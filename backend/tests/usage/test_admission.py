"""The admission of a model job (plan M1 5.6): in the transaction that starts it, an account with
no budget left starts none, one with MAX_JOBS_IN_FLIGHT waiting or running starts no more, and
starts beyond the minute's limit wait - starts side by side included."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from uuid import UUID

import psycopg
import pytest
from psycopg import errors

from app.core.ids import new_id
from app.db.accounts import create_account
from app.db.migrate import migrate
from app.db.rate_limits import RateLimited
from app.jobs.queue import account_lane, enqueue
from app.llm.metering import Spent
from app.usage.admission import NoBudget, TooManyJobs, admit_model_job
from app.usage.ledger import Charge, book, reserve

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

MODEL_KIND = "extraction.x1"
KINDS = frozenset({MODEL_KIND, "extraction.x4"})


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


async def an_account(
    connection: psycopg.AsyncConnection, token_limit: int | None = 10**6, *, role: str = "nutzer"
) -> UUID:
    """An account with a quota of ``token_limit`` (None: no limit); for 0 no quota row, which the
    ledger reads as a limit of nothing."""
    account = await create_account(connection, f"konto-{new_id().hex[-12:]}", [role])
    if token_limit != 0:
        await connection.execute(
            "INSERT INTO quota (account_id, token_limit) VALUES (%s, %s)", (account, token_limit)
        )
    return account


async def start(
    connection: psycopg.AsyncConnection,
    account: UUID,
    *,
    kind: str = MODEL_KIND,
    in_flight: int = 20,
    per_minute: int = 10,
) -> UUID:
    """Admit a model job and enqueue it, in one transaction, as an endpoint starting one does."""
    async with connection.transaction():
        await admit_model_job(
            connection, account, kinds=KINDS, max_in_flight=in_flight, starts_per_minute=per_minute
        )
        return await enqueue(connection, kind, account_lane(account))


async def test_an_account_with_budget_left_starts_a_model_job(connection: psycopg.AsyncConnection) -> None:
    limited, unlimited = await an_account(connection), await an_account(connection, token_limit=None)

    for account in (limited, unlimited):
        await start(connection, account)

    cursor = await connection.execute("SELECT count(*) FROM job WHERE kind = %s", (MODEL_KIND,))
    assert await cursor.fetchone() == (2,)


@pytest.mark.parametrize("role", ["nutzer", "admin"])
async def test_an_account_without_a_quota_starts_none(connection: psycopg.AsyncConnection, role: str) -> None:
    # an admin's model work is not free either: only a quota without a limit is (plan M1 5.6)
    account = await an_account(connection, token_limit=0, role=role)

    with pytest.raises(NoBudget):
        await start(connection, account)

    cursor = await connection.execute("SELECT count(*) FROM job")
    assert await cursor.fetchone() == (0,)


async def test_an_account_that_spent_its_budget_starts_none(connection: psycopg.AsyncConnection) -> None:
    account = await an_account(connection, token_limit=1_000)
    job = await enqueue(connection, "other.work", account_lane(account))
    charge = Charge(account_id=account, job_id=job, purpose="x1", model="gpt-6-luna")
    await book(
        connection, await reserve(connection, charge, 900, 100), Spent(input_tokens=900, output_tokens=100)
    )

    with pytest.raises(NoBudget):
        await start(connection, account)


async def test_jobs_in_flight_are_counted_up_to_the_limit(connection: psycopg.AsyncConnection) -> None:
    # waiting or running, of a model's kind, of the account: what it has started and not ended
    account, other = await an_account(connection), await an_account(connection)
    first = await start(connection, account, in_flight=2)
    running = await start(connection, account, kind="extraction.x4", in_flight=2)
    await connection.execute(
        "UPDATE job SET status = 'running', lease_owner = 'w', lease_token = gen_random_uuid(),"
        " lease_expires_at = now() + interval '1 minute' WHERE id = %s",
        (running,),
    )
    await enqueue(connection, "source.convert", account_lane(account))  # no model's
    await start(connection, other, in_flight=2)

    with pytest.raises(TooManyJobs) as refused:
        await start(connection, account, in_flight=2)

    assert refused.value.retry_after_s == 60
    await connection.execute("UPDATE job SET status = 'done' WHERE id = %s", (first,))
    await start(connection, account, in_flight=2)  # beside the running one, the conversion takes no place


async def test_starts_beyond_the_minute_s_limit_wait(connection: psycopg.AsyncConnection) -> None:
    account = await an_account(connection)
    for _ in range(2):
        await start(connection, account, per_minute=2)

    with pytest.raises(RateLimited):
        await start(connection, account, per_minute=2)


async def test_a_start_refused_takes_no_place_in_the_minute(connection: psycopg.AsyncConnection) -> None:
    account = await an_account(connection, token_limit=0)
    for _ in range(3):
        with pytest.raises(NoBudget):
            await start(connection, account, per_minute=2)
    await connection.execute("INSERT INTO quota (account_id, token_limit) VALUES (%s, NULL)", (account,))

    for _ in range(2):
        await start(connection, account, per_minute=2)


async def test_a_start_outside_the_starting_transaction_is_refused(
    connection: psycopg.AsyncConnection,
) -> None:
    # the account's lock holds to the end of the transaction that enqueues: none, none at all
    account = await an_account(connection)

    with pytest.raises(ValueError, match="transaction"):
        await admit_model_job(connection, account, kinds=KINDS, max_in_flight=20, starts_per_minute=10)


async def test_starts_side_by_side_never_exceed_the_jobs_in_flight(database_url: str) -> None:
    # twelve connections, all open, start at once where five may be in flight: five start
    migrate(database_url)
    async with AsyncExitStack() as opened:
        connections = [
            await opened.enter_async_context(
                await psycopg.AsyncConnection.connect(database_url, autocommit=True)
            )
            for _ in range(13)
        ]
        setup, side_by_side = connections[0], connections[1:]
        account = await an_account(setup)

        started = await asyncio.gather(
            *(start(own, account, in_flight=5, per_minute=100) for own in side_by_side),
            return_exceptions=True,
        )

        assert sorted(type(answer).__name__ for answer in started) == ["TooManyJobs"] * 7 + ["UUID"] * 5
        cursor = await setup.execute("SELECT count(*) FROM job WHERE lane = %s", (str(account),))
        assert await cursor.fetchone() == (5,)


async def test_what_calls_in_flight_hold_refuses_no_start(connection: psycopg.AsyncConnection) -> None:
    # their bookings give most of it back; the reservation of the start's first request decides
    account = await an_account(connection, token_limit=20_000)
    job = await enqueue(connection, "other.work", account_lane(account))
    charge = Charge(account_id=account, job_id=job, purpose="x1", model="gpt-6-luna")
    await reserve(connection, charge, 4_000, 16_000)  # all the limit, held

    await start(connection, account)


async def test_a_start_under_another_isolation_is_refused(database_url: str) -> None:
    # repeatable read counts the jobs there were when it began, before the account's lock was free
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as setup:
        account = await an_account(setup)
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

        with pytest.raises(errors.InvalidTransactionState, match="read committed"):
            await start(connection, account)
