"""A cancel ends its job even where the handler hangs (plan M1 7a, F6): the worker waits for the
handler CANCEL_WAIT_S at most, then ends the job cancelled and takes the next one; the handler,
left to unwind, writes nothing more - its lease is gone."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import migrate
from app.jobs import worker as workers
from app.jobs.queue import Job, LeaseLost, enqueue, hold_lease, request_cancel
from app.jobs.worker import Worker

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as opened:
        yield opened


async def status(pool: AsyncConnectionPool, job_id: UUID) -> tuple[Any, ...]:
    async with pool.connection() as connection:
        cursor = await connection.execute("SELECT status, result FROM job WHERE id = %s", (job_id,))
        found = await cursor.fetchone()
    assert found is not None
    return tuple(found)


async def test_a_handler_that_does_not_stop_at_its_cancel_holds_up_neither_its_job_nor_the_worker(
    pool: AsyncConnectionPool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(workers, "CANCEL_WAIT_S", 0.3)
    started, go_on, unwound = asyncio.Event(), asyncio.Event(), asyncio.Event()
    late_write: list[BaseException] = []

    async def stuck(job: Job) -> dict[str, Any]:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await go_on.wait()  # hangs on past its cancel, as a call that ignores it would
        try:
            async with pool.connection() as connection, connection.transaction():
                await hold_lease(connection, job)
                await connection.execute("UPDATE job SET result = '{}' WHERE id = %s", (job.id,))
        except LeaseLost as refused:
            late_write.append(refused)
        finally:
            unwound.set()
        return {"late": True}

    async def quick(job: Job) -> dict[str, Any]:
        return {"next": True}

    async with pool.connection() as connection:
        stuck_id = await enqueue(connection, "test.stuck", "account-a")
    worker = Worker(pool, {"test.stuck": stuck, "test.quick": quick}, owner="w1", lease_s=0.6)
    running = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), 5)
    async with pool.connection() as connection:
        await request_cancel(connection, stuck_id, "account-a")

    await asyncio.wait_for(running, 5)  # back within the cancel's wait, the handler still hanging

    assert await status(pool, stuck_id) == ("cancelled", None)
    async with pool.connection() as connection:
        quick_id = await enqueue(connection, "test.quick", "account-a")
    assert await worker.run_once() is True  # the worker takes the next job
    assert await status(pool, quick_id) == ("done", {"next": True})
    go_on.set()
    await asyncio.wait_for(unwound.wait(), 5)
    assert len(late_write) == 1  # the handler's late write found no lease
    assert await status(pool, stuck_id) == ("cancelled", None)


async def test_a_handler_that_stops_at_its_cancel_ends_its_job_as_before(pool: AsyncConnectionPool) -> None:
    started = asyncio.Event()

    async def obedient(job: Job) -> None:
        started.set()
        await asyncio.sleep(3600)

    async with pool.connection() as connection:
        job_id = await enqueue(connection, "test.obedient", "account-a")
    worker = Worker(pool, {"test.obedient": obedient}, owner="w1", lease_s=0.6)
    running = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), 5)
    async with pool.connection() as connection:
        await request_cancel(connection, job_id, "account-a")

    await asyncio.wait_for(running, 5)

    assert await status(pool, job_id) == ("cancelled", None)


def test_a_cancel_waits_for_its_handler_a_few_seconds_at_most() -> None:
    # long enough for a call to give up cleanly, short beside a lease
    assert 1 <= workers.CANCEL_WAIT_S <= 10
