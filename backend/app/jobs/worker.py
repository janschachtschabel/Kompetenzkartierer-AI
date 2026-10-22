"""The job worker: ``python -m app.jobs.worker`` runs the jobs the handlers know.

A worker claims one job at a time, runs its handler as a task and renews the lease at a third
of its length. A requested cancel or a lost lease cancels the handler; a lost lease writes
nothing, since the job is another worker's by then. How a job's end is written - its result, a
``PermanentError``, a retry - is app/jobs/outcome.py. Every third of a lease, busy or idle, the
worker hands expired leases back to the queue. A database away for a moment costs a warning,
not the worker: the claim waits for the next poll, an outcome is written again.

On SIGTERM the worker takes no new job and gives the running one JOB_SHUTDOWN_GRACE_S to
finish; then it cancels the handler and hands the job back unspent, for the next worker.

A handler must not block the event loop - the lease is renewed on it, and a blocked loop
loses it. CPU-heavy or blocking work goes through ``asyncio.to_thread`` or a process pool.
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

from app.jobs.outcome import Ending, Outcome, PermanentError, Result, one_line, write_outcome
from app.jobs.queue import Job, LeaseLost, claim, heartbeat, requeue_expired

__all__ = ["Handler", "PermanentError", "Result", "Worker", "main"]

log = logging.getLogger("app.jobs.worker")  # also when run as __main__

Handler = Callable[[Job], Coroutine[Any, Any, Result]]
# How long a cancelled handler may take to unwind before its job goes back anyway: the deployment
# kills the pod at the end of its grace, and a kill would count the attempt after all
RELEASE_WAIT_S = 2.0


class Worker:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        handlers: Mapping[str, Handler],
        *,
        owner: str,
        lease_s: float = 60.0,
        poll_s: float = 1.0,
        grace_s: float = 20.0,
    ) -> None:
        self.pool = pool
        self.handlers = handlers
        self.owner = owner
        self.lease_s = lease_s
        self.poll_s = poll_s
        self.grace_s = grace_s
        self._stop = asyncio.Event()  # run's; run_once alone never stops
        # set when the sweep of expired leases broke: the process ends with an error then
        self.broken = False

    async def run(self, stop: asyncio.Event) -> None:
        """Work until ``stop`` is set; the job running then gets ``grace_s`` to finish."""
        self._stop = stop
        sweeper = asyncio.create_task(self._sweep_until(stop))
        sweeper.add_done_callback(self._stop_when_broken)
        try:
            while not stop.is_set():
                try:
                    if await self.run_once():
                        continue
                except (psycopg.Error, PoolTimeout) as error:
                    log.warning("could not claim a job: %s", one_line(error))
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), self.poll_s)
        finally:
            sweeper.cancel()
            await asyncio.gather(sweeper, return_exceptions=True)

    async def run_once(self) -> bool:
        """Claim and run one job; ``False`` if none waited."""
        if not self.handlers:  # nothing to take: an empty list of kinds still read the queue
            return False
        async with self.pool.connection() as connection:
            job = await claim(connection, self.owner, list(self.handlers), self.lease_s)
        if job is None:
            return False
        if self._stop.is_set():  # told to stop while the claim was on its way: not started, back
            await self._write(job, None, "released")
            return True
        await self._run(job)
        return True

    async def _run(self, job: Job) -> None:
        task: asyncio.Task[Result] = asyncio.create_task(self.handlers[job.kind](job))
        try:
            ending = await self._keep_alive(job, task)
        finally:
            if not task.done():  # this worker itself is being cancelled
                task.cancel()
        if ending == "released":
            # handed back whatever the handler does with its cancel; its outcome is not wanted,
            # but a failure on the way out is said, by its type - asyncio would log its words
            task.add_done_callback(lambda finished: _report_unwinding(job, finished))
            await asyncio.wait({task}, timeout=RELEASE_WAIT_S)
            await self._write(job, None, ending)
            return
        outcomes: tuple[Outcome] = await asyncio.gather(task, return_exceptions=True)
        [outcome] = outcomes
        if ending == "lost":
            log.warning("lost the lease of job %s (%s); another worker has it", job.id, job.kind)
            return
        await self._write(job, outcome, ending)

    async def _keep_alive(self, job: Job, task: asyncio.Task[Any]) -> Ending:
        """Renew the lease while the handler runs; how it was stopped, if it was.

        Once the worker is told to stop, the handler gets ``grace_s`` before it is cancelled.
        """
        loop = asyncio.get_running_loop()
        beat_s = self.lease_s / 3
        next_beat = loop.time() + beat_s
        deadline: float | None = None
        stopping = asyncio.ensure_future(self._stop.wait())
        try:
            while not task.done():
                wake = next_beat if deadline is None else min(next_beat, deadline)
                waiting = {task} if stopping.done() else {task, stopping}
                await asyncio.wait(
                    waiting, timeout=max(0.0, wake - loop.time()), return_when=asyncio.FIRST_COMPLETED
                )
                if task.done():
                    return None
                if stopping.done() and deadline is None:
                    deadline = loop.time() + self.grace_s
                    log.info("stopping: job %s (%s) gets %.0f s to finish", job.id, job.kind, self.grace_s)
                if deadline is not None and loop.time() >= deadline:
                    task.cancel()
                    return "released"
                if loop.time() >= next_beat:
                    next_beat = loop.time() + beat_s
                    ending = await self._beat(job, task)
                    if ending is not None:
                        return ending
            return None
        finally:
            stopping.cancel()

    async def _beat(self, job: Job, task: asyncio.Task[Any]) -> Ending:
        try:
            async with self.pool.connection() as connection:
                cancel_requested = await heartbeat(connection, job, self.lease_s)
        except LeaseLost:
            task.cancel()
            return "lost"
        except (psycopg.Error, PoolTimeout) as error:
            # the database is away for a moment: the next beat may still be in time
            log.warning("could not renew the lease of job %s: %s", job.id, one_line(error))
            return None
        if cancel_requested:
            task.cancel()
            return "cancelled"
        return None

    async def _write(self, job: Job, outcome: Outcome, ending: Ending) -> None:
        await write_outcome(self.pool, job, outcome, ending, lease_s=self.lease_s)

    def _stop_when_broken(self, sweeper: asyncio.Task[None]) -> None:
        """A sweeper that died of something unforeseen stops the worker: without it every dead
        worker's job would stay stranded, and a restarted pod sweeps again."""
        if sweeper.cancelled() or sweeper.exception() is None:
            return
        log.error("the sweep of expired leases broke; the worker stops", exc_info=sweeper.exception())
        self.broken = True
        self._stop.set()

    async def _sweep_until(self, stop: asyncio.Event) -> None:
        """Hand expired leases back every third of a lease, whether this worker is busy or not."""
        while not stop.is_set():
            await self._hand_back_expired()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.lease_s / 3)

    async def _hand_back_expired(self) -> None:
        try:
            async with self.pool.connection() as connection:
                handed_back = await requeue_expired(connection)
        except (psycopg.Error, PoolTimeout) as error:
            log.warning("could not look for expired leases: %s", one_line(error))
            return
        if handed_back:
            log.info("handed %d job(s) with an expired lease back", handed_back)


def _report_unwinding(job: Job, handler: asyncio.Task[Any]) -> None:
    if handler.cancelled() or handler.exception() is None:
        return
    log.warning(
        "the handler of job %s (%s) failed while it stopped: %s",
        job.id,
        job.kind,
        type(handler.exception()).__name__,
    )


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
        worker = Worker(
            pool,
            HANDLERS,
            owner=owner,
            lease_s=settings.job_lease_s,
            poll_s=settings.job_poll_s,
            grace_s=settings.job_shutdown_grace_s,
        )
        log.info("worker %s takes %s", owner, sorted(HANDLERS) or "nothing")
        await worker.run(stop)
    finally:
        await pool.close()
    # a supervisor restarts a worker that ended with an error
    return 1 if worker.broken else 0


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
    from app.llm.client import check_reasoning_effort
    from app.llm.settings import LLMSettings

    settings = Settings()
    llm = LLMSettings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stdout)
    try:
        check_reasoning_effort(llm)
    except ValueError as error:
        log.error("%s", error)
        return 1
    # psycopg's async mode needs a selector loop; Windows' default is the proactor
    return asyncio.run(_serve(), loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    sys.exit(main())
