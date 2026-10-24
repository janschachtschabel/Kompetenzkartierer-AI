"""A job of a unique key (plan M1 7a, F2): enqueued while another of its key waits or runs, it is
not made - the caller learns the open one; once that has ended, the key takes a new job."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest

from app.db.migrate import migrate
from app.jobs import queue
from app.jobs.queue import OpenJob, claim, complete, enqueue, last_jobs, open_job, request_cancel

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

KEY = "extract.run:01900000-0000-7000-8000-000000000001"
OTHER = "extract.run:01900000-0000-7000-8000-000000000002"


@pytest.fixture
async def connect(database_url: str) -> AsyncIterator[Any]:
    migrate(database_url)
    opened: list[psycopg.AsyncConnection] = []

    async def make(autocommit: bool = True) -> psycopg.AsyncConnection:
        connection = await psycopg.AsyncConnection.connect(database_url, autocommit=autocommit)
        opened.append(connection)
        return connection

    yield make
    for connection in opened:
        await connection.close()


async def count(connection: psycopg.AsyncConnection, key: str) -> int:
    cursor = await connection.execute("SELECT count(*) FROM job WHERE unique_key = %s", (key,))
    found = await cursor.fetchone()
    assert found is not None
    return int(found[0])


async def test_a_job_of_a_key_whose_job_is_open_is_not_made_and_names_the_open_one(connect: Any) -> None:
    db = await connect()
    first = await enqueue(db, "test.work", "account-a", unique_key=KEY)

    with pytest.raises(OpenJob) as refused:
        await enqueue(db, "test.work", "account-b", unique_key=KEY)  # whoever asks

    assert refused.value.job_id == first
    assert await count(db, KEY) == 1
    assert await open_job(db, KEY) == first


async def test_a_running_job_holds_its_key_too(connect: Any) -> None:
    db = await connect()
    first = await enqueue(db, "test.work", "account-a", unique_key=KEY)
    assert await claim(db, "worker-1", ("test.work",), 30) is not None

    with pytest.raises(OpenJob) as refused:
        await enqueue(db, "test.work", "account-a", unique_key=KEY)

    assert refused.value.job_id == first


async def test_once_its_job_has_ended_the_key_takes_a_new_one(connect: Any) -> None:
    db = await connect()
    done = await enqueue(db, "test.work", "account-a", unique_key=KEY)
    job = await claim(db, "worker-1", ("test.work",), 30)
    assert job is not None
    await complete(db, job, {"ok": True})
    cancelled = await enqueue(db, "test.work", "account-a", unique_key=KEY)
    assert await request_cancel(db, cancelled, "account-a") is True

    newest = await enqueue(db, "test.work", "account-a", unique_key=KEY)

    assert await open_job(db, KEY) == newest
    assert await last_jobs(db, [KEY, OTHER]) == {KEY: (newest, "queued")}
    assert len({done, cancelled, newest}) == 3


async def test_a_key_without_any_job_has_none(connect: Any) -> None:
    db = await connect()

    assert await open_job(db, KEY) is None
    assert await last_jobs(db, [KEY]) == {}


async def test_jobs_without_a_key_are_made_as_ever(connect: Any) -> None:
    db = await connect()

    made = {await enqueue(db, "test.work", "account-a") for _ in range(3)}

    assert len(made) == 3


async def waiting_on_a_lock(look: psycopg.AsyncConnection, pid: int) -> None:
    for _ in range(200):
        cursor = await look.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", (pid,))
        found = await cursor.fetchone()
        if found is not None and found[0] == "Lock":
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the second start never waited on the first's row")


@pytest.mark.parametrize("first_commits", [True, False], ids=["committed", "rolled-back"])
async def test_of_two_starts_side_by_side_one_makes_the_job(connect: Any, first_commits: bool) -> None:
    # the second waits on the first's row in the unique index, then sees what became of it
    first_db, second_db = await connect(autocommit=False), await connect(autocommit=False)
    first = await enqueue(first_db, "test.work", "account-a", unique_key=KEY)

    async def second_start() -> Any:
        try:
            made = await enqueue(second_db, "test.work", "account-b", unique_key=KEY)
        except OpenJob as refused:
            await second_db.rollback()
            return refused
        await second_db.commit()
        return made

    second = asyncio.create_task(second_start())
    await waiting_on_a_lock(await connect(), second_db.info.backend_pid)
    await (first_db.commit() if first_commits else first_db.rollback())
    outcome = await asyncio.wait_for(second, 10)

    if first_commits:
        assert isinstance(outcome, OpenJob) and outcome.job_id == first
    else:
        assert outcome != first and not isinstance(outcome, OpenJob)
    assert await count(await connect(), KEY) == 1


async def test_a_start_whose_open_job_ends_before_it_looks_for_it_makes_the_new_job(
    connect: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, other = await connect(), await connect()
    first = await enqueue(db, "test.work", "account-a", unique_key=KEY)
    looked: list[str] = []

    async def ended_meanwhile(connection: psycopg.AsyncConnection, key: str) -> Any:
        if not looked:  # the insert gave way to it; it ends before the look
            await other.execute(
                "UPDATE job SET status = 'cancelled', finished_at = now() WHERE id = %s", (first,)
            )
        looked.append(key)
        return await open_job(connection, key)

    monkeypatch.setattr(queue, "open_job", ended_meanwhile)

    made = await enqueue(db, "test.work", "account-a", unique_key=KEY)

    assert made != first and await open_job(db, KEY) == made
    assert looked == [KEY]


async def test_a_start_that_never_finds_the_job_it_gave_way_to_gives_up(
    connect: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = await connect()
    await enqueue(db, "test.work", "account-a", unique_key=KEY)

    async def never(connection: psycopg.AsyncConnection, key: str) -> None:
        return None

    monkeypatch.setattr(queue, "open_job", never)

    with pytest.raises(RuntimeError, match="kept ending"):
        await enqueue(db, "test.work", "account-a", unique_key=KEY)
    assert await count(db, KEY) == 1
