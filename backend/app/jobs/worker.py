"""The job worker: ``python -m app.jobs.worker`` runs the jobs the handlers know.

A worker claims one job at a time, runs its handler as a task and renews the lease at a third
of its length. A requested cancel or a lost lease cancels the handler; a lost lease writes
nothing, since the job is another worker's by then. A ``PermanentError`` ends the job; any
other error is retried, keeping only the error's type - its text may quote input. An idle
worker hands expired leases back to the queue. On SIGTERM it takes no new job and lets the
running one finish; the deployment's grace period should outlast the longest job's lease.
"""

import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

import psycopg
from psycopg_pool import AsyncConnectionPool, PoolTimeout

from app.jobs.queue import Job, LeaseLost, claim, complete, fail, heartbeat, mark_cancelled, requeue_expired

log = logging.getLogger("app.jobs.worker")  # also when run as __main__

Result = dict[str, Any] | None
Handler = Callable[[Job], Coroutine[Any, Any, Result]]
Outcome = Result | BaseException


class PermanentError(Exception):
    """A failure another attempt cannot cure (bad input); ``message`` is kept, so no secrets."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Worker:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        handlers: Mapping[str, Handler],
        *,
        owner: str,
        lease_s: float = 60.0,
        poll_s: float = 1.0,
    ) -> None:
        self.pool = pool
        self.handlers = handlers
        self.owner = owner
        self.lease_s = lease_s
        self.poll_s = poll_s

    async def run(self, stop: asyncio.Event) -> None:
        """Work until ``stop`` is set; the job running then is finished first."""
        while not stop.is_set():
            if await self.run_once():
                continue
            await self._hand_back_expired()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.poll_s)

    async def run_once(self) -> bool:
        """Claim and run one job; ``False`` if none waited."""
        async with self.pool.connection() as connection:
            job = await claim(connection, self.owner, list(self.handlers), self.lease_s)
        if job is None:
            return False
        await self._run(job)
        return True

    async def _run(self, job: Job) -> None:
        task: asyncio.Task[Result] = asyncio.create_task(self.handlers[job.kind](job))
        try:
            ending = await self._keep_alive(job, task)
        finally:
            if not task.done():  # this worker itself is being cancelled
                task.cancel()
        outcomes: tuple[Outcome] = await asyncio.gather(task, return_exceptions=True)
        [outcome] = outcomes
        if ending == "lost":
            log.warning("lost the lease of job %s (%s); another worker has it", job.id, job.kind)
            return
        try:
            async with self.pool.connection() as connection:
                await self._record(connection, job, outcome, cancelled=ending == "cancelled")
        except LeaseLost:
            log.warning("lost the lease of job %s (%s) at its end; its outcome is dropped", job.id, job.kind)

    async def _keep_alive(self, job: Job, task: asyncio.Task[Any]) -> str | None:
        """Renew the lease while the handler runs; ``"cancelled"`` or ``"lost"`` if it was stopped."""
        while not task.done():
            await asyncio.wait({task}, timeout=self.lease_s / 3)
            if task.done():
                return None
            try:
                async with self.pool.connection() as connection:
                    cancel_requested = await heartbeat(connection, job, self.lease_s)
            except LeaseLost:
                task.cancel()
                return "lost"
            except (psycopg.Error, PoolTimeout) as error:
                # the database is away for a moment: the next beat may still be in time
                log.warning("could not renew the lease of job %s: %s", job.id, " ".join(str(error).split()))
                continue
            if cancel_requested:
                task.cancel()
                return "cancelled"
        return None

    async def _record(
        self, connection: psycopg.AsyncConnection, job: Job, outcome: Outcome, *, cancelled: bool
    ) -> None:
        if cancelled:
            await mark_cancelled(connection, job)
        elif isinstance(outcome, PermanentError):
            await fail(connection, job, outcome.code, outcome.message, retry=False)
        elif isinstance(outcome, BaseException):
            log.error("job %s (%s) failed", job.id, job.kind, exc_info=outcome)
            await fail(connection, job, "handler_error", type(outcome).__name__, retry=True)
        else:
            await complete(connection, job, outcome)

    async def _hand_back_expired(self) -> None:
        try:
            async with self.pool.connection() as connection:
                handed_back = await requeue_expired(connection)
        except (psycopg.Error, PoolTimeout) as error:
            log.warning("could not look for expired leases: %s", " ".join(str(error).split()))
            return
        if handed_back:
            log.info("handed %d job(s) with an expired lease back", handed_back)


async def _serve() -> int:
    from app.core.settings import Settings
    from app.db.pool import create_pool
    from app.jobs.handlers import HANDLERS

    settings = Settings()
    stop = asyncio.Event()
    _stop_on_signals(stop)
    if not HANDLERS:
        log.warning("no job handlers are registered: the worker idles")
    pool = create_pool(settings)
    await pool.open(wait=False)
    try:
        owner = f"{socket.gethostname()}:{os.getpid()}"
        worker = Worker(pool, HANDLERS, owner=owner, lease_s=settings.job_lease_s, poll_s=settings.job_poll_s)
        log.info("worker %s takes %s", owner, sorted(HANDLERS) or "nothing")
        await worker.run(stop)
    finally:
        await pool.close()
    return 0


def _stop_on_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for name in ("SIGTERM", "SIGINT"):
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            loop.add_signal_handler(number, stop.set)
        except NotImplementedError:  # Windows: no signal handlers on the loop
            signal.signal(number, lambda *_: loop.call_soon_threadsafe(stop.set))


def main() -> int:
    from app.core.logging import configure_logging
    from app.core.settings import Settings

    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stdout)
    # psycopg's async mode needs a selector loop; Windows' default is the proactor
    return asyncio.run(_serve(), loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    sys.exit(main())
