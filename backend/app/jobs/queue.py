"""The job queue on the ``job`` table.

A claim takes one waiting job with ``FOR UPDATE SKIP LOCKED``, so workers never take the same
one, and prefers the lane (account) with the fewest running jobs, then the oldest job: one
account with many jobs does not hold back the others. The claim sets a lease; the owner renews
it with ``heartbeat`` and learns there of a requested cancel. Only the lease's owner can finish
a job; a worker that lost its lease (too slow, cut off) gets ``LeaseLost`` and must drop its
result, another worker has the job by then. ``requeue_expired`` hands expired leases back to
the queue while attempts remain. Every statement stands alone (the connections run in
autocommit), and every time is the database's ``now()``.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.ids import new_id

# Wait before the next attempt: 10 s, 20 s, 40 s, ... at most 10 min
_BACKOFF = "make_interval(secs => least(10 * power(2, greatest(attempts - 1, 0)), 600))"


class LeaseLost(Exception):
    """The job's lease is no longer this worker's: it expired, or the job ended."""


@dataclass(frozen=True)
class Job:
    id: UUID
    kind: str
    lane: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    lease_owner: str


async def enqueue(
    connection: psycopg.AsyncConnection,
    kind: str,
    lane: str,
    payload: dict[str, Any] | None = None,
    *,
    max_attempts: int = 3,
    run_after_s: float = 0,
) -> UUID:
    job_id = new_id()
    await connection.execute(
        "INSERT INTO job (id, kind, lane, payload, max_attempts, run_after)"
        " VALUES (%s, %s, %s, %s, %s, now() + make_interval(secs => %s))",
        (job_id, kind, lane, Jsonb(payload or {}), max_attempts, run_after_s),
    )
    return job_id


async def claim(
    connection: psycopg.AsyncConnection, owner: str, kinds: Collection[str], lease_s: float
) -> Job | None:
    """One waiting job of ``kinds``, now running under ``owner``'s lease; ``None`` if none waits."""
    cursor = connection.cursor(row_factory=dict_row)
    await cursor.execute(
        """
        WITH running AS (
            SELECT lane, count(*) AS jobs FROM job WHERE status = 'running' GROUP BY lane
        ), chosen AS (
            SELECT job.id FROM job LEFT JOIN running ON running.lane = job.lane
            WHERE job.status = 'queued' AND job.run_after <= now() AND job.kind = ANY(%(kinds)s)
            ORDER BY coalesce(running.jobs, 0), job.created_at
            LIMIT 1
            FOR UPDATE OF job SKIP LOCKED
        )
        UPDATE job SET status = 'running', lease_owner = %(owner)s,
            lease_expires_at = now() + make_interval(secs => %(lease)s),
            attempts = job.attempts + 1, started_at = coalesce(job.started_at, now())
        FROM chosen WHERE job.id = chosen.id
        RETURNING job.id, job.kind, job.lane, job.payload, job.attempts, job.max_attempts, job.lease_owner
        """,
        {"kinds": list(kinds), "owner": owner, "lease": lease_s},
    )
    found = await cursor.fetchone()
    return Job(**found) if found else None


async def heartbeat(connection: psycopg.AsyncConnection, job: Job, lease_s: float) -> bool:
    """Renew the lease; ``True`` if a cancel was requested. Raises ``LeaseLost``."""
    cursor = await connection.execute(
        "UPDATE job SET lease_expires_at = now() + make_interval(secs => %s)"
        " WHERE id = %s AND lease_owner = %s AND status = 'running' RETURNING cancel_requested",
        (lease_s, job.id, job.lease_owner),
    )
    found = await cursor.fetchone()
    if found is None:
        raise LeaseLost(str(job.id))
    return bool(found[0])


async def complete(connection: psycopg.AsyncConnection, job: Job, result: dict[str, Any] | None) -> None:
    await _finish(connection, job, "status = 'done', result = %s", (Jsonb(result),))


async def mark_cancelled(connection: psycopg.AsyncConnection, job: Job) -> None:
    await _finish(connection, job, "status = 'cancelled'", ())


async def fail(
    connection: psycopg.AsyncConnection, job: Job, code: str, message: str, *, retry: bool
) -> Literal["queued", "failed"]:
    """Record the failure; the job waits for another attempt if ``retry`` and attempts remain."""
    cursor = await connection.execute(
        f"""
        UPDATE job SET error = %s, lease_owner = NULL, lease_expires_at = NULL,
            status = CASE WHEN %s AND attempts < max_attempts AND NOT cancel_requested
                          THEN 'queued' ELSE 'failed' END,
            run_after = CASE WHEN %s THEN now() + {_BACKOFF} ELSE run_after END,
            finished_at = CASE WHEN %s AND attempts < max_attempts AND NOT cancel_requested
                               THEN NULL ELSE now() END
        WHERE id = %s AND lease_owner = %s AND status = 'running'
        RETURNING status
        """,  # noqa: S608 - _BACKOFF is a constant expression
        (Jsonb({"code": code, "message": message}), retry, retry, retry, job.id, job.lease_owner),
    )
    found = await cursor.fetchone()
    if found is None:
        raise LeaseLost(str(job.id))
    status: Literal["queued", "failed"] = found[0]
    return status


async def request_cancel(connection: psycopg.AsyncConnection, job_id: UUID) -> bool:
    """Mark a waiting or running job for cancelling; a waiting one ends now. ``False`` if it had ended."""
    cursor = await connection.execute(
        """
        UPDATE job SET cancel_requested = true,
            status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
            finished_at = CASE WHEN status = 'queued' THEN now() ELSE finished_at END
        WHERE id = %s AND status IN ('queued', 'running')
        RETURNING id
        """,
        (job_id,),
    )
    return await cursor.fetchone() is not None


async def requeue_expired(connection: psycopg.AsyncConnection) -> int:
    """Hand jobs whose lease expired back to the queue, or end them; how many were touched."""
    cursor = await connection.execute(
        f"""
        UPDATE job SET lease_owner = NULL, lease_expires_at = NULL,
            status = CASE WHEN cancel_requested THEN 'cancelled'
                          WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
            run_after = now() + {_BACKOFF},
            error = CASE WHEN cancel_requested OR attempts < max_attempts THEN error
                         ELSE jsonb_build_object('code', 'lease_lost',
                              'message', 'the worker stopped renewing its lease') END,
            finished_at = CASE WHEN NOT cancel_requested AND attempts < max_attempts THEN NULL ELSE now() END
        WHERE status = 'running' AND lease_expires_at < now()
        """  # noqa: S608 - _BACKOFF is a constant expression
    )
    return cursor.rowcount


async def _finish(
    connection: psycopg.AsyncConnection, job: Job, assignment: str, values: tuple[Any, ...]
) -> None:
    cursor = await connection.execute(
        f"UPDATE job SET {assignment}, lease_owner = NULL, lease_expires_at = NULL, finished_at = now()"  # noqa: S608
        " WHERE id = %s AND lease_owner = %s AND status = 'running' RETURNING id",
        (*values, job.id, job.lease_owner),
    )
    if await cursor.fetchone() is None:
        raise LeaseLost(str(job.id))
