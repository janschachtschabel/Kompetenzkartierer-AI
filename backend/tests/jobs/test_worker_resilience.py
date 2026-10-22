"""The worker keeps going: it sweeps on time and rides out database gaps and bad results.
Stopping is in test_worker_shutdown.py."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import migrate
from app.jobs import outcome as outcome_module
from app.jobs import worker as worker_module
from app.jobs.queue import Job, complete, enqueue
from app.jobs.worker import Worker
from tests.support import FAKE_DATABASE_URL

pytestmark = pytest.mark.anyio
DEADLINE_S = 5.0


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as opened:
        yield opened


async def job_row(pool: AsyncConnectionPool, job_id: UUID) -> dict[str, Any]:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT status, attempts, error, lease_owner, run_after > now() FROM job WHERE id = %s", (job_id,)
        )
        found = await cursor.fetchone()
    assert found is not None
    return dict(zip(["status", "attempts", "error", "owner", "later"], found, strict=True))


async def add(
    pool: AsyncConnectionPool, kind: str = "test.work", payload: dict[str, Any] | None = None
) -> UUID:
    async with pool.connection() as connection:
        return await enqueue(connection, kind, "account-a", payload or {})


def deeply_nested(depth: int) -> dict[str, Any]:
    root: dict[str, Any] = {}
    level = root
    for _ in range(depth):
        level["x"] = {}
        level = level["x"]
    return root


async def until(check: Callable[[], Awaitable[bool]]) -> None:
    deadline = asyncio.get_running_loop().time() + DEADLINE_S
    while not await check():
        assert asyncio.get_running_loop().time() < deadline, "timed out"
        await asyncio.sleep(0.05)


@pytest.mark.pg
async def test_expired_leases_go_back_while_the_worker_is_busy(pool: AsyncConnectionPool) -> None:
    # one busy worker must not leave a dead worker's job stranded until it is idle again
    started, release = asyncio.Event(), asyncio.Event()

    async def long_job(job: Job) -> None:
        started.set()
        await release.wait()

    stranded = await add(pool, kind="test.other")
    async with pool.connection() as connection:
        # it expires while the worker is busy: a sweep at the start alone would miss it
        await connection.execute(
            "UPDATE job SET status = 'running', lease_owner = 'gone', lease_token = gen_random_uuid(),"
            " lease_expires_at = now() + interval '0.3 s', attempts = 1 WHERE id = %s",
            (stranded,),
        )
    await add(pool)
    stop = asyncio.Event()
    running = asyncio.create_task(
        Worker(pool, {"test.work": long_job}, owner="w1", lease_s=0.6, poll_s=0.05).run(stop)
    )
    await asyncio.wait_for(started.wait(), DEADLINE_S)

    async def handed_back() -> bool:
        return bool((await job_row(pool, stranded))["status"] == "queued")

    try:
        await until(handed_back)
    finally:
        release.set()
        stop.set()
        await asyncio.wait_for(running, DEADLINE_S)


@pytest.mark.pg
async def test_a_job_three_leases_long_keeps_its_lease_and_ends_done(pool: AsyncConnectionPool) -> None:
    # the worker's own sweep runs every third of a lease: without renewal it would take the job.
    # 1.2 s, so a loop or database stalled for a moment under load does not lose the lease
    lease_s = 1.2
    returned = asyncio.Event()

    async def long_job(job: Job) -> dict[str, Any]:
        await asyncio.sleep(3 * lease_s)
        returned.set()
        return {"done": True}

    job_id = await add(pool)
    stop = asyncio.Event()
    worker = Worker(pool, {"test.work": long_job}, owner="w1", lease_s=lease_s, poll_s=0.05)
    running = asyncio.create_task(worker.run(stop))

    async def written() -> bool:
        return bool((await job_row(pool, job_id))["status"] != "running")

    try:
        await asyncio.wait_for(returned.wait(), DEADLINE_S)
        await until(written)
    finally:
        stop.set()
        await asyncio.wait_for(running, DEADLINE_S)

    found = await job_row(pool, job_id)
    assert (found["status"], found["attempts"]) == ("done", 1)


@pytest.mark.pg
@pytest.mark.parametrize(
    "bad",
    # no JSON (a UUID, NaN, too deep to write), or JSON the database refuses (NUL, a lone surrogate)
    [uuid.uuid4(), float("nan"), deeply_nested(5000), "a" + chr(0) + "b", "a" + chr(0xD800) + "b"],
    ids=["uuid", "nan", "too-deep", "nul", "surrogate"],
)
async def test_a_result_that_is_no_json_fails_its_job_and_the_worker_goes_on(
    pool: AsyncConnectionPool, bad: object
) -> None:
    async def answer(job: Job) -> dict[str, Any]:
        return {"value": bad} if job.payload.get("bad") else {"value": 1}

    broken = await add(pool, payload={"bad": True})
    worker = Worker(pool, {"test.work": answer}, owner="w1")

    assert await worker.run_once() is True
    fine = await add(pool)
    assert await worker.run_once() is True

    found = await job_row(pool, broken)
    # failed at once, not run again: another attempt would return the same result
    assert (found["status"], found["attempts"], found["error"]["code"]) == (
        "failed",
        1,
        "result_not_storable",
    )
    assert (await job_row(pool, fine))["status"] == "done"


async def test_the_worker_rides_out_a_database_that_is_away(caplog: pytest.LogCaptureFixture) -> None:
    async def anything(job: Job) -> None:
        return None

    stop = asyncio.Event()
    async with AsyncConnectionPool(
        FAKE_DATABASE_URL, min_size=0, max_size=2, timeout=0.2, open=False
    ) as away:
        running = asyncio.create_task(
            Worker(away, {"test.work": anything}, owner="w1", poll_s=0.05).run(stop)
        )
        await asyncio.sleep(1.0)
        still_working = not running.done()
        stop.set()
        await asyncio.wait_for(running, DEADLINE_S)

    assert still_working
    assert sum("could not claim" in record.getMessage() for record in caplog.records) >= 2


@pytest.mark.pg
async def test_an_outcome_is_written_after_a_brief_database_error(
    pool: AsyncConnectionPool, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def flaky_complete(connection: Any, job: Job, result: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise psycopg.OperationalError("the server closed the connection (invented)")
        await complete(connection, job, result)

    async def answer(job: Job) -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setattr(outcome_module, "complete", flaky_complete)
    job_id = await add(pool)

    await Worker(pool, {"test.work": answer}, owner="w1", lease_s=0.9).run_once()

    assert (calls, (await job_row(pool, job_id))["status"]) == (2, "done")


@pytest.mark.pg
async def test_a_sweeper_that_breaks_stops_the_worker_and_says_why(
    pool: AsyncConnectionPool, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # a worker that went on without its sweep would strand every dead worker's job
    async def broken_sweep(connection: Any) -> list[str]:
        raise RuntimeError("invented")

    async def anything(job: Job) -> None:
        return None

    monkeypatch.setattr(worker_module, "requeue_expired", broken_sweep)
    stop = asyncio.Event()
    worker = Worker(pool, {"test.work": anything}, owner="w1", poll_s=0.05)
    running = asyncio.create_task(worker.run(stop))

    done, _ = await asyncio.wait({running}, timeout=DEADLINE_S)

    assert running in done
    assert stop.is_set()
    # the process ends with an error, so a supervisor restarts it
    assert worker.broken
    assert any(record.levelname == "ERROR" and "sweep" in record.getMessage() for record in caplog.records)


async def test_a_worker_without_handlers_asks_the_database_nothing() -> None:
    # M0 has no handlers yet: polling with an empty list of kinds read every waiting job
    async with AsyncConnectionPool(
        FAKE_DATABASE_URL, min_size=0, max_size=1, timeout=0.2, open=False
    ) as away:
        assert await Worker(away, {}, owner="w1").run_once() is False


@pytest.mark.pg
@pytest.mark.parametrize(
    "text", ["page 3: 'a" + chr(0) + "b'", "page 3: 'a" + chr(0xD800) + "b'"], ids=["nul", "surrogate"]
)
async def test_a_permanent_failure_whose_words_the_database_refuses_still_ends_the_job(
    pool: AsyncConnectionPool, text: str
) -> None:
    # its message quotes the input; refused as jsonb, the job ran again and again
    async def refuse(job: Job) -> None:
        raise worker_module.PermanentError("bad_input", text)

    job_id = await add(pool)

    await Worker(pool, {"test.work": refuse}, owner="w1").run_once()

    found = await job_row(pool, job_id)
    assert (found["status"], found["attempts"], found["error"]["code"]) == ("failed", 1, "bad_input")
    assert chr(0) not in found["error"]["message"]


@pytest.mark.pg
async def test_a_result_too_deep_for_the_database_s_writer_fails_its_job_and_the_worker_goes_on(
    pool: AsyncConnectionPool, monkeypatch: pytest.MonkeyPatch
) -> None:
    # past the JSON check but too deep for psycopg's own writer, deeper in the stack
    async def too_deep(connection: Any, job: Job, result: Any) -> None:
        raise RecursionError("maximum recursion depth exceeded while encoding a JSON object")

    async def answer(job: Job) -> dict[str, Any]:
        return {"value": 1}

    monkeypatch.setattr(outcome_module, "complete", too_deep)
    broken = await add(pool)
    worker = Worker(pool, {"test.work": answer}, owner="w1")

    assert await worker.run_once() is True

    found = await job_row(pool, broken)
    assert (found["status"], found["error"]["code"]) == ("failed", "result_not_storable")
