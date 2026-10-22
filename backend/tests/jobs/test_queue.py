"""The job queue in PostgreSQL: claimed once, fairly across lanes, held by a lease."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import psycopg
import pytest

from app.core.ids import new_id
from app.db.migrate import migrate
from app.jobs.queue import (
    LeaseLost,
    claim,
    complete,
    enqueue,
    fail,
    heartbeat,
    mark_cancelled,
    release,
    request_cancel,
    requeue_expired,
)

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

LEASE_S = 30.0
KINDS = ("test.work",)


@pytest.fixture
async def connect(database_url: str) -> AsyncIterator[Any]:
    migrate(database_url)
    opened: list[psycopg.AsyncConnection] = []

    async def make() -> psycopg.AsyncConnection:
        connection = await psycopg.AsyncConnection.connect(database_url, autocommit=True)
        opened.append(connection)
        return connection

    yield make
    for connection in opened:
        await connection.close()


async def row(connection: psycopg.AsyncConnection, job_id: object) -> dict[str, Any]:
    cursor = await connection.execute(
        "SELECT status, attempts, lease_owner, result, error, cancel_requested,"
        " run_after > now() AS later FROM job WHERE id = %s",
        (job_id,),
    )
    found = await cursor.fetchone()
    assert found is not None
    names = [column.name for column in cursor.description or []]
    return dict(zip(names, found, strict=True))


async def test_a_job_is_claimed_once_and_held_by_its_owner(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a", {"n": 1})

    job = await claim(db, "worker-1", KINDS, LEASE_S)

    assert job is not None
    assert (job.id, job.kind, job.lane, job.payload, job.attempts) == (
        job_id,
        "test.work",
        "account-a",
        {"n": 1},
        1,
    )
    assert (await row(db, job_id))["status"] == "running"
    assert await claim(db, "worker-2", KINDS, LEASE_S) is None


async def test_a_job_for_later_or_of_another_kind_is_not_claimed(connect: Any) -> None:
    db = await connect()
    await enqueue(db, "test.work", "account-a", run_after_s=3600)
    await enqueue(db, "test.other", "account-a")

    assert await claim(db, "worker-1", KINDS, LEASE_S) is None


async def test_the_lane_with_fewer_running_jobs_goes_first(connect: Any) -> None:
    db = await connect()
    first_a = await enqueue(db, "test.work", "account-a")
    second_a = await enqueue(db, "test.work", "account-a")
    only_b = await enqueue(db, "test.work", "account-b")

    order = [job.id for job in [await claim(db, f"w{i}", KINDS, LEASE_S) for i in range(3)] if job]

    # one busy account does not hold back the others: b's newer job comes before a's second
    assert order == [first_a, only_b, second_a]


async def test_lanes_take_turns_when_each_job_ends_before_the_next_claim(connect: Any) -> None:
    # one worker, nothing left running: the lane served longest ago comes next, not the oldest job
    db = await connect()
    a0, a1, _ = [await enqueue(db, "test.work", "account-a") for _ in range(3)]
    b0 = await enqueue(db, "test.work", "account-b")

    order = []
    for _ in range(3):
        job = await claim(db, "worker-1", KINDS, LEASE_S)
        assert job is not None
        order.append(job.id)
        await complete(db, job, None)

    assert order == [a0, b0, a1]


async def test_a_claim_passes_over_a_job_another_claim_is_taking(connect: Any, database_url: str) -> None:
    db = await connect()
    taking = await enqueue(db, "test.work", "account-a")
    free = await enqueue(db, "test.work", "account-b")
    # another claim's transaction holds the first job's row, as a claim does until it commits
    async with await psycopg.AsyncConnection.connect(database_url) as other:
        await other.execute("SELECT id FROM job WHERE id = %s FOR UPDATE", (taking,))

        job = await asyncio.wait_for(claim(db, "worker-2", KINDS, LEASE_S), timeout=5)

    assert job is not None
    assert job.id == free


async def test_a_lane_another_claim_is_stamping_holds_up_neither_a_claim_nor_an_enqueue(
    connect: Any, database_url: str
) -> None:
    # a peer stuck between its stamp and its commit (a lost node, a paused VM) held the lane for
    # every worker and every enqueue of that account until the server noticed it gone
    db = await connect()
    await enqueue(db, "test.work", "account-a")
    await enqueue(db, "test.work", "account-b")
    async with await psycopg.AsyncConnection.connect(database_url) as stuck:
        await stuck.execute("UPDATE job_lane SET served_at = now() WHERE lane = 'account-a'")

        job = await asyncio.wait_for(claim(db, "worker-2", KINDS, LEASE_S), timeout=5)
        added = await asyncio.wait_for(enqueue(db, "test.work", "account-a"), timeout=5)

    assert job is not None
    assert (await row(db, added))["status"] == "queued"


async def test_the_owner_completes_a_job_and_a_stranger_cannot(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")
    job = await claim(db, "worker-1", KINDS, LEASE_S)
    assert job is not None

    assert await heartbeat(db, job, LEASE_S) is False
    stranger = job.__class__(**{**job.__dict__, "lease_token": new_id()})
    with pytest.raises(LeaseLost):
        await heartbeat(db, stranger, LEASE_S)
    with pytest.raises(LeaseLost):
        await complete(db, stranger, {"x": 1})
    await complete(db, job, {"pages": 3})

    assert (await row(db, job_id))["status"] == "done"
    assert (await row(db, job_id))["result"] == {"pages": 3}


async def test_an_expired_lease_goes_back_to_the_queue_and_the_old_owner_is_refused(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")
    lost = await claim(db, "worker-1", KINDS, 0.2)
    assert lost is not None
    await asyncio.sleep(0.5)

    assert await requeue_expired(db) == ["queued"]
    # it waits out the backoff first: a job that killed its worker may kill the next one too
    assert (await row(db, job_id))["later"] is True
    await db.execute("UPDATE job SET run_after = now() WHERE id = %s", (job_id,))
    taken = await claim(db, "worker-2", KINDS, LEASE_S)

    assert taken is not None
    assert (taken.id, taken.attempts) == (job_id, 2)
    with pytest.raises(LeaseLost):
        await complete(db, lost, {})


async def test_a_heartbeat_moves_the_lease_on(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")
    job = await claim(db, "worker-1", KINDS, LEASE_S)
    assert job is not None

    await heartbeat(db, job, 600)

    cursor = await db.execute(
        "SELECT lease_expires_at - now() > interval '500 s' FROM job WHERE id = %s", (job_id,)
    )
    assert await cursor.fetchone() == (True,)


async def test_a_claim_under_a_reused_owner_name_is_not_the_old_one(connect: Any) -> None:
    # host:pid repeats after a restart; the lease is told apart by its token, not the name
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")
    old = await claim(db, "host:1", KINDS, 0.2)
    assert old is not None
    await asyncio.sleep(0.5)
    await requeue_expired(db)
    await db.execute("UPDATE job SET run_after = now() WHERE id = %s", (job_id,))
    new = await claim(db, "host:1", KINDS, LEASE_S)
    assert new is not None

    with pytest.raises(LeaseLost):
        await complete(db, old, {"stale": True})
    await complete(db, new, {"fresh": True})

    assert (await row(db, job_id))["result"] == {"fresh": True}


async def test_attempts_are_bounded(connect: Any) -> None:
    db = await connect()

    with pytest.raises(psycopg.errors.CheckViolation):
        await enqueue(db, "test.work", "account-a", max_attempts=101)


async def test_a_job_with_very_many_attempts_does_not_break_the_backoff(connect: Any) -> None:
    # 10 * 2^attempts overflowed past some 1,020 attempts, and the sweep failed for every job
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")
    assert await claim(db, "worker-1", KINDS, 0.2) is not None
    await db.execute("UPDATE job SET attempts = 2000 WHERE id = %s", (job_id,))
    await asyncio.sleep(0.5)

    assert await requeue_expired(db) == ["failed"]
    assert (await row(db, job_id))["status"] == "failed"


async def test_a_failure_after_a_cancel_request_ends_cancelled(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a", max_attempts=3)
    job = await claim(db, "worker-1", KINDS, LEASE_S)
    assert job is not None
    await request_cancel(db, job_id, "account-a")

    assert await fail(db, job, "converter_down", "the converter did not answer", retry=True) == "cancelled"
    assert (await row(db, job_id))["status"] == "cancelled"


async def test_a_released_job_waits_again_unspent_unless_its_cancel_was_asked(connect: Any) -> None:
    db = await connect()
    kept = await enqueue(db, "test.work", "account-a")
    dropped = await enqueue(db, "test.work", "account-b")
    first = await claim(db, "worker-1", KINDS, LEASE_S)
    second = await claim(db, "worker-1", KINDS, LEASE_S)
    assert first is not None and second is not None
    await request_cancel(db, dropped, "account-b")

    await release(db, first)
    await release(db, second)

    assert {key: (await row(db, kept))[key] for key in ("status", "attempts", "lease_owner", "later")} == {
        "status": "queued",
        "attempts": 0,
        "lease_owner": None,
        "later": False,
    }
    assert (await row(db, dropped))["status"] == "cancelled"
    with pytest.raises(LeaseLost):
        await release(db, first)


async def test_an_expired_lease_on_the_last_attempt_fails_the_job(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a", max_attempts=1)
    assert await claim(db, "worker-1", KINDS, 0.2) is not None
    await asyncio.sleep(0.5)

    await requeue_expired(db)

    found = await row(db, job_id)
    assert found["status"] == "failed"
    assert found["error"]["code"] == "lease_lost"


async def test_a_failure_is_retried_later_until_the_last_attempt(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a", max_attempts=2)
    job = await claim(db, "worker-1", KINDS, LEASE_S)
    assert job is not None

    assert await fail(db, job, "converter_down", "the converter did not answer", retry=True) == "queued"
    after_first = await row(db, job_id)
    await db.execute("UPDATE job SET run_after = now() WHERE id = %s", (job_id,))
    again = await claim(db, "worker-1", KINDS, LEASE_S)
    assert again is not None
    assert await fail(db, again, "converter_down", "the converter did not answer", retry=True) == "failed"

    assert (after_first["status"], after_first["later"]) == ("queued", True)
    final = await row(db, job_id)
    assert (final["status"], final["error"]) == (
        "failed",
        {"code": "converter_down", "message": "the converter did not answer"},
    )


async def test_a_failure_that_cannot_pass_is_not_retried(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a", max_attempts=5)
    job = await claim(db, "worker-1", KINDS, LEASE_S)
    assert job is not None

    assert await fail(db, job, "bad_input", "the file is no PDF", retry=False) == "failed"
    assert (await row(db, job_id))["attempts"] == 1


async def test_a_waiting_job_cancelled_never_runs(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")

    assert await request_cancel(db, job_id, "account-a") is True
    assert await claim(db, "worker-1", KINDS, LEASE_S) is None
    assert (await row(db, job_id))["status"] == "cancelled"
    assert await request_cancel(db, job_id, "account-a") is False


async def test_a_cancel_from_another_lane_changes_nothing(connect: Any) -> None:
    # who may cancel is decided in the statement itself, not by a check before it
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")

    assert await request_cancel(db, job_id, "account-b") is False
    assert {key: (await row(db, job_id))[key] for key in ("status", "cancel_requested")} == {
        "status": "queued",
        "cancel_requested": False,
    }
    assert await request_cancel(db, job_id, "account-a") is True


async def test_an_admin_s_cancel_reaches_every_lane(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")

    assert await request_cancel(db, job_id, None) is True
    assert (await row(db, job_id))["status"] == "cancelled"


async def test_a_running_job_learns_of_its_cancel_at_its_heartbeat(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")
    job = await claim(db, "worker-1", KINDS, LEASE_S)
    assert job is not None

    assert await request_cancel(db, job_id, "account-a") is True
    assert await heartbeat(db, job, LEASE_S) is True
    await mark_cancelled(db, job)

    assert (await row(db, job_id))["status"] == "cancelled"


async def test_an_expired_lease_of_a_cancelled_job_ends_it(connect: Any) -> None:
    db = await connect()
    job_id = await enqueue(db, "test.work", "account-a")
    assert await claim(db, "worker-1", KINDS, 0.2) is not None
    await request_cancel(db, job_id, "account-a")
    await asyncio.sleep(0.5)

    assert await requeue_expired(db) == ["cancelled"]

    assert (await row(db, job_id))["status"] == "cancelled"
