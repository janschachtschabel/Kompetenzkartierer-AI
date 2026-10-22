"""One request per host every CHECK_HOST_INTERVAL_S, across all workers (plan M1, 2.5).

Before each request a worker takes the host's next slot in host_throttle: the later of the host's
next time and now, which moves one interval on. Workers asking at once queue on the row's lock
and take slots one interval apart; every time is the database's, so the workers' clocks do not
matter. The worker then sleeps until its slot. A server that asks to wait (Retry-After) holds its
host off for as long; a host whose next turn lies further off than a worker will wait gives no
turn at all, and its addresses wait for a later check.
"""

import asyncio
import math
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
_HOLD = """
    INSERT INTO host_throttle AS throttle (host, next_at)
    VALUES (%(host)s, clock_timestamp() + make_interval(secs => %(seconds)s))
    ON CONFLICT (host) DO UPDATE SET next_at = greatest(throttle.next_at, EXCLUDED.next_at)
"""


async def take_turn(
    connection: psycopg.AsyncConnection, host: str, interval_s: float, *, max_wait_s: float = math.inf
) -> float | None:
    """The seconds until the slot now taken for ``host``; none or less: now. None, and no slot taken,
    where the host's next turn lies further off than ``max_wait_s``. The slot holds once the
    connection's transaction is committed.

    The slot is taken first and given back where it lies too far off: a turn read before it is
    taken may be held off meanwhile by another worker (hold_host), on a row the read found none of
    to lock."""
    try:
        async with connection.transaction():
            cursor = await connection.execute(_TAKE, {"host": host, "interval": interval_s})
            found = await cursor.fetchone()
            assert found is not None  # noqa: S101 - an upsert returns its row
            wait = float(found[0])
            if wait > max_wait_s:
                raise _TooFar
    except _TooFar:
        return None
    return wait


class _TooFar(Exception):
    """The host's next turn lies further off than the worker waits: the slot is given back."""


async def hold_host(connection: psycopg.AsyncConnection, host: str, seconds: float) -> None:
    """Give ``host`` no turn for ``seconds``, as its server asked; a later turn already taken stays."""
    await connection.execute(_HOLD, {"host": host, "seconds": seconds})


async def wait_turn(
    pool: AsyncConnectionPool,
    host: str,
    interval_s: float,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_wait_s: float = math.inf,
) -> bool:
    """Take ``host``'s next slot and wait for it; False, without a slot, where it lies further off
    than ``max_wait_s``."""
    async with pool.connection() as connection:
        wait = await take_turn(connection, host, interval_s, max_wait_s=max_wait_s)
    if wait is None:
        return False
    if wait > 0:
        await sleep(wait)
    return True
