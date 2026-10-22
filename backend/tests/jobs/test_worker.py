"""The worker runs claimed jobs, keeps their lease alive and writes their outcome."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import migrate
from app.jobs.queue import Job, enqueue, request_cancel
from app.jobs.worker import PermanentError, Worker

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as opened:
        yield opened


async def state(pool: AsyncConnectionPool, job_id: UUID) -> dict[str, Any]:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT status, result, error, lease_owner, run_after > now() FROM job WHERE id = %s", (job_id,)
        )
        found = await cursor.fetchone()
    assert found is not None
    return dict(zip(["status", "result", "error", "owner", "later"], found, strict=True))


async def add(pool: AsyncConnectionPool, kind: str = "test.work", **options: Any) -> UUID:
    async with pool.connection() as connection:
        return await enqueue(connection, kind, "account-a", {"n": 1}, **options)


async def test_a_job_runs_and_its_result_is_kept(pool: AsyncConnectionPool) -> None:
    async def double(job: Job) -> dict[str, Any]:
        return {"twice": job.payload["n"] * 2}

    job_id = await add(pool)

    assert await Worker(pool, {"test.work": double}, owner="w1").run_once() is True
    assert await state(pool, job_id) == {
        "status": "done",
        "result": {"twice": 2},
        "error": None,
        "owner": None,
        "later": False,
    }


async def test_a_worker_takes_only_kinds_it_handles(pool: AsyncConnectionPool) -> None:
    async def anything(job: Job) -> None:
        return None

    await add(pool, kind="test.other")

    assert await Worker(pool, {"test.work": anything}, owner="w1").run_once() is False


async def test_a_permanent_error_ends_the_job_without_retry(pool: AsyncConnectionPool) -> None:
    async def refuse(job: Job) -> None:
        raise PermanentError("bad_input", "the file is no PDF")

    job_id = await add(pool, max_attempts=3)
    await Worker(pool, {"test.work": refuse}, owner="w1").run_once()

    found = await state(pool, job_id)
    assert (found["status"], found["error"]) == (
        "failed",
        {"code": "bad_input", "message": "the file is no PDF"},
    )


async def test_an_unexpected_error_is_retried_and_its_text_not_kept(pool: AsyncConnectionPool) -> None:
    async def crash(job: Job) -> None:
        raise ValueError("secret input text")

    job_id = await add(pool, max_attempts=3)
    await Worker(pool, {"test.work": crash}, owner="w1").run_once()

    found = await state(pool, job_id)
    assert (found["status"], found["later"]) == ("queued", True)
    assert found["error"] == {"code": "handler_error", "message": "ValueError"}


async def test_a_cancel_stops_the_running_handler(pool: AsyncConnectionPool) -> None:
    started, stopped = asyncio.Event(), asyncio.Event()

    async def wait_forever(job: Job) -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            stopped.set()
            raise

    job_id = await add(pool)
    worker = Worker(pool, {"test.work": wait_forever}, owner="w1", lease_s=0.6)
    running = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), 5)
    async with pool.connection() as connection:
        await request_cancel(connection, job_id, "account-a")

    await asyncio.wait_for(running, 5)

    assert stopped.is_set()
    assert (await state(pool, job_id))["status"] == "cancelled"


async def test_a_worker_that_lost_its_lease_stops_and_writes_nothing(pool: AsyncConnectionPool) -> None:
    started = asyncio.Event()

    async def slow(job: Job) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(3600)
        return {"late": True}

    job_id = await add(pool)
    worker = Worker(pool, {"test.work": slow}, owner="w1", lease_s=0.6)
    running = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), 5)
    async with pool.connection() as connection:
        # another worker took the job over after the lease ran out
        await connection.execute(
            "UPDATE job SET lease_owner = 'w2', lease_token = gen_random_uuid() WHERE id = %s", (job_id,)
        )

    await asyncio.wait_for(running, 5)

    found = await state(pool, job_id)
    assert (found["status"], found["owner"], found["result"]) == ("running", "w2", None)


async def test_a_stopped_worker_finishes_its_job_and_takes_no_new_one(pool: AsyncConnectionPool) -> None:
    stop = asyncio.Event()

    async def stop_during(job: Job) -> dict[str, Any]:
        stop.set()
        await asyncio.sleep(0.1)
        return {"finished": True}

    first, second = await add(pool), await add(pool)
    await asyncio.wait_for(Worker(pool, {"test.work": stop_during}, owner="w1", poll_s=0.05).run(stop), 10)

    assert (await state(pool, first))["status"] == "done"
    assert (await state(pool, second))["status"] == "queued"


async def test_an_idle_worker_hands_expired_leases_back(pool: AsyncConnectionPool, database_url: str) -> None:
    job_id = await add(pool)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as connection:
        await connection.execute(
            "UPDATE job SET status = 'running', lease_owner = 'gone', lease_token = gen_random_uuid(),"
            " lease_expires_at = now() - interval '1 s', attempts = 1 WHERE id = %s",
            (job_id,),
        )
    stop = asyncio.Event()
    worker = Worker(pool, {"test.other": lambda job: asyncio.sleep(0)}, owner="w1", poll_s=0.05)
    running = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(running, 5)

    assert (await state(pool, job_id))["status"] == "queued"
