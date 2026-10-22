"""How a job's end is written: its result, its failure, its cancel, or its return to the queue.

A ``PermanentError`` ends the job; any other error is retried, keeping only the error's type -
its text may quote input. A result that is no JSON, or JSON the database refuses, fails the job
(``result_not_storable``): another attempt would return the same. A database away for a moment
gets WRITE_ATTEMPTS tries; past them the outcome is lost, and the job runs again once its lease
expires.
"""

import asyncio
import json
import logging
from typing import Any, Literal

import psycopg
from psycopg_pool import AsyncConnectionPool

from app.jobs.queue import Job, LeaseLost, complete, fail, mark_cancelled, release

log = logging.getLogger("app.jobs.worker")  # the worker's lines, wherever they are written

Result = dict[str, Any] | None
Outcome = Result | BaseException
# How a job's run ended other than by its handler: asked to cancel, lease lost, handed back
Ending = Literal["cancelled", "lost", "released"] | None
# Tries to write an outcome while the database is away, within a third of the lease
WRITE_ATTEMPTS = 3
# What a database away for a moment raises (PoolTimeout is an OperationalError); anything else -
# a value the database refuses, a fault in a query - would only fail the same way again
TRANSIENT = (psycopg.OperationalError, psycopg.InterfaceError)


class PermanentError(Exception):
    """A failure another attempt cannot cure (bad input); ``message`` is kept, so no secrets."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def one_line(error: BaseException) -> str:
    return " ".join(str(error).split())


async def write_outcome(
    pool: AsyncConnectionPool, job: Job, outcome: Outcome, ending: Ending, *, lease_s: float
) -> None:
    """Record how the job ended; a database away for a moment gets WRITE_ATTEMPTS tries."""
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        try:
            async with pool.connection() as connection:
                if ending == "released":
                    await release(connection, job)
                else:
                    await _record(connection, job, outcome, cancelled=ending == "cancelled")
            return
        except LeaseLost:
            log.warning("lost the lease of job %s (%s) at its end; its outcome is dropped", job.id, job.kind)
            return
        except TRANSIENT as error:
            if attempt == WRITE_ATTEMPTS:
                log.error(
                    "could not write the outcome of job %s (%s): %s; it runs again after its lease",
                    job.id,
                    job.kind,
                    one_line(error),
                )
                return
            log.warning("could not write the outcome of job %s yet: %s", job.id, one_line(error))
            await asyncio.sleep(lease_s / 9)
        except psycopg.Error as error:
            # the type and state only: the database's message may quote the result
            log.error(
                "could not write the outcome of job %s (%s): %s %s; it runs again after its lease",
                job.id,
                job.kind,
                type(error).__name__,
                error.sqlstate,
            )
            return


async def _record(
    connection: psycopg.AsyncConnection, job: Job, outcome: Outcome, *, cancelled: bool
) -> None:
    if cancelled:
        await mark_cancelled(connection, job)
    elif isinstance(outcome, PermanentError):
        await fail(connection, job, outcome.code, outcome.message, retry=False)
    elif isinstance(outcome, BaseException):
        log.error("job %s (%s) failed", job.id, job.kind, exc_info=outcome)
        await fail(connection, job, "handler_error", type(outcome).__name__, retry=True)
    else:
        try:
            # as the database will take it: no NaN, no type JSON does not know, not too deep
            json.dumps(outcome, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as error:
            log.error(
                "job %s (%s) returned a result that is no JSON: %s", job.id, job.kind, type(error).__name__
            )
            await fail(connection, job, "result_not_storable", type(error).__name__, retry=False)
            return
        try:
            # in a block of its own (a savepoint inside an open transaction), so the
            # connection is still good to record the failure
            async with connection.transaction():
                await complete(connection, job, outcome)
        except (psycopg.DataError, RecursionError) as error:
            # JSON the database refuses (a NUL, a lone surrogate), or too deep for psycopg's own
            # writer, which runs deeper in the stack than the check above. Another attempt would
            # return the same; the type only, the message quotes the result
            log.error(
                "job %s (%s) returned a result the database refuses: %s",
                job.id,
                job.kind,
                type(error).__name__,
            )
            await fail(connection, job, "result_not_storable", type(error).__name__, retry=False)
