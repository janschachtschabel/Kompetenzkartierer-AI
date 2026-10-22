"""One request per host every CHECK_HOST_INTERVAL_S, across all workers (plan M1, 2.5).

Before each request a worker takes the host's next slot in host_throttle: the later of the host's
next time and now, which moves one interval on. Workers asking at once queue on the row's lock
and take slots one interval apart; every time is the database's, so the workers' clocks do not
matter. The worker then sleeps until its slot.
"""

import asyncio
from collections.abc import Awaitable, Callable

import psycopg
from psycopg_pool import AsyncConnectionPool

_TAKE = """
    INSERT INTO host_throttle AS throttle (host, next_at)
    VALUES (%(host)s, clock_timestamp() + make_interval(secs => %(interval)s))
    ON CONFLICT (host) DO UPDATE
        SET next_at = greatest(throttle.next_at, clock_timestamp()) + make_interval(secs => %(interval)s)
    RETURNING extract(epoch FROM throttle.next_at - make_interval(secs => %(interval)s) - clock_timestamp())
"""


async def take_turn(connection: psycopg.AsyncConnection, host: str, interval_s: float) -> float:
    """The seconds until the slot now taken for ``host``; none or less: now. The slot holds once
    the connection's transaction is committed."""
    cursor = await connection.execute(_TAKE, {"host": host, "interval": interval_s})
    found = await cursor.fetchone()
    assert found is not None  # noqa: S101 - an upsert returns its row
    return float(found[0])


async def wait_turn(
    pool: AsyncConnectionPool,
    host: str,
    interval_s: float,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Take ``host``'s next slot and wait for it."""
    async with pool.connection() as connection:
        wait = await take_turn(connection, host, interval_s)
    if wait > 0:
        await sleep(wait)
