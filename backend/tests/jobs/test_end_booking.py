"""A job's open reservations are booked when it ends (plan M1, Nachtrag 5, Festlegungen für Paket 6):
by the transaction that ends its attempt under its lease - done, failed, cancelled, handed back -
and, for an attempt whose worker died or lost its lease, by the sweep of expired leases."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from psycopg_pool import AsyncConnectionPool

from app.core.ids import new_id
from app.db.accounts import create_account
from app.db.migrate import migrate
from app.jobs.outcome import Ending, Outcome, PermanentError, write_outcome
from app.jobs.queue import Job, account_lane, claim, enqueue
from app.jobs.worker import Worker
from app.usage.ledger import Charge, reserve

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
KIND = "extract.run"


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as opened:
        yield opened


async def a_running_job_holding(pool: AsyncConnectionPool) -> Job:
    """A job of an account claimed by a worker, with a reservation of its attempt open."""
    async with pool.connection() as connection:
        account = await create_account(connection, f"konto-{new_id().hex[-12:]}", ["nutzer"])
        await connection.execute("INSERT INTO quota (account_id, token_limit) VALUES (%s, NULL)", (account,))
        await enqueue(connection, KIND, account_lane(account))
        job = await claim(connection, "w1", [KIND], 60)
        assert job is not None
        await connection.commit()  # a reservation is made alone, as a stage makes it
        await reserve(connection, Charge(account, job.id, "x1.profile", "gpt-6-luna"), 300, 200)
    return job


async def held_and_booked(pool: AsyncConnectionPool, job_id: UUID) -> tuple[int, list[Any]]:
    async with pool.connection() as connection:
        cursor = await connection.execute(
            "SELECT count(*) FROM usage_reservation WHERE job_id = %s", (job_id,)
        )
        held = await cursor.fetchone()
        cursor = await connection.execute(
            "SELECT input_tokens, output_tokens, unanswered_requests, estimated FROM llm_usage"
            " WHERE job_id = %s",
            (job_id,),
        )
        booked = await cursor.fetchall()
    assert held is not None
    return held[0], booked


@pytest.mark.parametrize(
    ("outcome", "ending"),
    [
        ({"done": True}, None),
        (PermanentError("budget_exhausted", "the budget is spent"), None),
        (RuntimeError("asked again"), None),
        (None, "cancelled"),
        (None, "released"),
    ],
    ids=["done", "failed", "retried", "cancelled", "released"],
)
async def test_the_end_of_an_attempt_books_what_it_left_open(
    pool: AsyncConnectionPool, outcome: Outcome, ending: Ending
) -> None:
    job = await a_running_job_holding(pool)

    assert await write_outcome(pool, job, outcome, ending, lease_s=60)

    assert await held_and_booked(pool, job.id) == (0, [(300, 200, 1, True)])


async def test_an_end_without_its_lease_books_nothing(pool: AsyncConnectionPool) -> None:
    # the attempt that took the lease since holds the job's reservations now
    job = await a_running_job_holding(pool)
    async with pool.connection() as connection:
        await connection.execute("UPDATE job SET lease_token = gen_random_uuid() WHERE id = %s", (job.id,))

    assert not await write_outcome(pool, job, {"done": True}, None, lease_s=60)

    assert await held_and_booked(pool, job.id) == (1, [])


async def test_the_sweep_books_what_an_attempt_of_a_dead_worker_left_open(pool: AsyncConnectionPool) -> None:
    job = await a_running_job_holding(pool)
    async with pool.connection() as connection:
        await connection.execute(
            "UPDATE job SET lease_expires_at = now() - interval '1 s' WHERE id = %s", (job.id,)
        )
    stop = asyncio.Event()
    worker = Worker(pool, {"test.other": lambda job: asyncio.sleep(0)}, owner="w2", poll_s=0.05)
    running = asyncio.create_task(worker.run(stop))
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(running, 5)

    assert await held_and_booked(pool, job.id) == (0, [(300, 200, 1, True)])
