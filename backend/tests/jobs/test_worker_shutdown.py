"""A stopping worker: the running job gets its grace, then goes back unspent, for the next worker."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import migrate
from app.jobs import worker as worker_module
from app.jobs.queue import Job, claim, enqueue
from app.jobs.worker import Worker

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
DEADLINE_S = 5.0
UNSPENT = {"status": "queued", "attempts": 0, "owner": None, "later": False}


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as opened:
        yield opened


async def job_row(pool: AsyncConnectionPool, job_id: UUID) -> dict[str, Any]:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT status, attempts, lease_owner, run_after > now() FROM job WHERE id = %s", (job_id,)
        )
        found = await cursor.fetchone()
    assert found is not None
    return dict(zip(["status", "attempts", "owner", "later"], found, strict=True))


async def add(pool: AsyncConnectionPool) -> UUID:
    async with pool.connection() as connection:
        return await enqueue(connection, "test.work", "account-a", {})


async def test_a_job_past_the_shutdown_grace_goes_back_unspent(pool: AsyncConnectionPool) -> None:
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def endless(job: Job) -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    job_id = await add(pool)
    stop = asyncio.Event()
    worker = Worker(pool, {"test.work": endless}, owner="w1", lease_s=3, poll_s=0.05, grace_s=0.3)
    running = asyncio.create_task(worker.run(stop))
    await asyncio.wait_for(started.wait(), DEADLINE_S)

    stop.set()
    await asyncio.wait_for(running, DEADLINE_S)

    assert cancelled.is_set()
    assert await job_row(pool, job_id) == UNSPENT


async def test_a_handler_slow_to_stop_does_not_hold_its_job_past_the_deployment_s_grace(
    pool: AsyncConnectionPool,
) -> None:
    # one that tidies up at length, or swallows the cancel, must not keep the job from going back
    # before the kill that would count the attempt after all
    started, tidied = asyncio.Event(), asyncio.Event()

    async def stubborn(job: Job) -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await tidied.wait()

    job_id = await add(pool)
    stop = asyncio.Event()
    worker = Worker(pool, {"test.work": stubborn}, owner="w1", lease_s=3, poll_s=0.05, grace_s=0.3)
    running = asyncio.create_task(worker.run(stop))
    await asyncio.wait_for(started.wait(), DEADLINE_S)

    stop.set()
    done, _ = await asyncio.wait({running}, timeout=DEADLINE_S)
    tidied.set()

    assert running in done
    assert await job_row(pool, job_id) == UNSPENT


async def test_a_job_claimed_as_the_worker_is_told_to_stop_goes_back_unrun(
    pool: AsyncConnectionPool, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[Job] = []
    stop = asyncio.Event()

    async def claim_then_sigterm(*args: Any, **kwargs: Any) -> Job | None:
        job = await claim(*args, **kwargs)
        stop.set()  # SIGTERM arrives while the claim is on its way
        return job

    async def handler(job: Job) -> None:
        ran.append(job)

    monkeypatch.setattr(worker_module, "claim", claim_then_sigterm)
    job_id = await add(pool)

    await asyncio.wait_for(
        Worker(pool, {"test.work": handler}, owner="w1", poll_s=0.05).run(stop), DEADLINE_S
    )

    assert ran == []
    assert await job_row(pool, job_id) == UNSPENT
