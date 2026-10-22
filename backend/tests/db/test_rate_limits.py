"""Limits per account and minute (uploads, URL imports, model jobs), kept in the database: the API
replicas share them, and requests at the same moment cannot slip past together."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import psycopg
import pytest

from app.db.accounts import create_account
from app.db.migrate import migrate
from app.db.rate_limits import RateLimited, take

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


async def account(connection: psycopg.AsyncConnection, name: str = "Lehrkraft") -> UUID:
    return await create_account(connection, name, ["nutzer"])


async def test_an_account_takes_up_to_its_limit_and_then_waits(connection: psycopg.AsyncConnection) -> None:
    who = await account(connection)
    for _ in range(3):
        await take(connection, who, "source.upload", per_minute=3)

    with pytest.raises(RateLimited) as limited:
        await take(connection, who, "source.upload", per_minute=3)

    assert 1 <= limited.value.retry_after_s <= 60


async def test_each_account_and_each_action_has_its_own_count(connection: psycopg.AsyncConnection) -> None:
    first, second = await account(connection, "Eins"), await account(connection, "Zwei")
    await take(connection, first, "source.upload", per_minute=1)

    await take(connection, second, "source.upload", per_minute=1)
    await take(connection, first, "source.import", per_minute=1)


async def test_what_was_taken_a_minute_ago_counts_no_more(connection: psycopg.AsyncConnection) -> None:
    who = await account(connection)
    await connection.execute(
        "INSERT INTO rate_event (account_id, action, at)"
        " VALUES (%s, 'source.upload', now() - interval '61 seconds')",
        (who,),
    )

    await take(connection, who, "source.upload", per_minute=1)


async def test_requests_at_the_same_moment_do_not_slip_past_together(database_url: str) -> None:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as setup:
        who = await account(setup)

    async def one() -> bool:
        async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as connection:
            try:
                await take(connection, who, "source.upload", per_minute=5)
            except RateLimited:
                return False
            return True

    outcomes = await asyncio.gather(*(one() for _ in range(12)))

    assert outcomes.count(True) == 5
