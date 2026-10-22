"""One request per host every CHECK_HOST_INTERVAL_S, across all workers (plan M1, 2.5): each takes
the host's next slot in host_throttle and waits for it."""

import asyncio
from collections.abc import AsyncIterator
from itertools import pairwise

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import migrate
from app.sources.throttle import hold_host, take_turn, wait_turn

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

HOST = "lehrplaene.example"


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=8, open=False) as opened:
        yield opened


async def turn(pool: AsyncConnectionPool, host: str = HOST, interval_s: float = 1.0) -> float:
    async with pool.connection() as connection:
        wait = await take_turn(connection, host, interval_s)
    assert wait is not None  # a host no server held off has a turn
    return wait


async def test_a_host_s_first_turn_is_now(pool: AsyncConnectionPool) -> None:
    assert await turn(pool) <= 0


async def test_the_next_turn_comes_one_interval_later(pool: AsyncConnectionPool) -> None:
    await turn(pool)

    wait = await turn(pool)

    assert 0.8 < wait <= 1.0


async def test_hosts_take_their_turns_apart(pool: AsyncConnectionPool) -> None:
    await turn(pool, "a.example")

    assert await turn(pool, "b.example") <= 0


async def test_turns_taken_at_once_by_many_workers_are_one_interval_apart(pool: AsyncConnectionPool) -> None:
    waits = sorted(await asyncio.gather(*(turn(pool, interval_s=0.5) for _ in range(6))))

    assert waits[0] <= 0
    gaps = [later - earlier for earlier, later in pairwise(waits)]
    assert all(0.45 < gap < 0.55 for gap in gaps), waits


async def test_a_host_left_alone_longer_than_the_interval_has_its_turn_now(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as connection:
        await connection.execute(
            "INSERT INTO host_throttle (host, next_at) VALUES (%s, now() - interval '1 hour')", (HOST,)
        )

    assert await turn(pool) <= 0
    # and the one after waits as ever: the hour gone by is no credit
    assert 0.8 < await turn(pool) <= 1.0


async def test_a_worker_waits_for_its_turn(pool: AsyncConnectionPool) -> None:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    await wait_turn(pool, HOST, 2.0, sleep=sleep)
    await wait_turn(pool, HOST, 2.0, sleep=sleep)

    assert len(slept) == 1 and 1.8 < slept[0] <= 2.0


async def test_the_turn_is_kept_when_the_worker_s_connection_is_returned(database_url: str) -> None:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url) as first:
        await take_turn(first, HOST, 1.0)
    async with await psycopg.AsyncConnection.connect(database_url) as second:
        wait = await take_turn(second, HOST, 1.0)
    assert wait is not None and wait > 0.8


async def test_a_host_held_by_its_server_has_no_turn_soon(pool: AsyncConnectionPool) -> None:
    # Retry-After: the host is not asked before its server said
    async with pool.connection() as connection:
        await hold_host(connection, HOST, 3600)
        wait = await take_turn(connection, HOST, 1.0, max_wait_s=120)
        other = await take_turn(connection, "b.example", 1.0, max_wait_s=120)

    assert wait is None
    assert other is not None and other <= 0


async def test_a_turn_not_taken_moves_nothing(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as connection:
        await hold_host(connection, HOST, 300)
        assert await take_turn(connection, HOST, 1.0, max_wait_s=120) is None
        cursor = await connection.execute(
            "SELECT extract(epoch FROM next_at - clock_timestamp()) FROM host_throttle WHERE host = %s",
            (HOST,),
        )
        found = await cursor.fetchone()

    assert found is not None and 295 < float(found[0]) <= 300


async def test_a_hold_shorter_than_the_turns_ahead_changes_nothing(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as connection:
        for _ in range(3):
            await take_turn(connection, HOST, 10.0)
        await hold_host(connection, HOST, 5)
        wait = await take_turn(connection, HOST, 10.0)

    assert wait is not None and 25 < wait <= 30


async def test_a_worker_hears_when_a_host_waits_too_long(pool: AsyncConnectionPool) -> None:
    async def sleep(seconds: float) -> None:
        raise AssertionError("slept for a host held off")

    async with pool.connection() as connection:
        await hold_host(connection, HOST, 3600)

    assert await wait_turn(pool, HOST, 2.0, sleep=sleep, max_wait_s=120) is False
    assert await wait_turn(pool, "b.example", 2.0, sleep=sleep, max_wait_s=120) is True
