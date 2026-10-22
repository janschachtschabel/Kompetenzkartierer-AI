"""Limits per account and minute, kept in PostgreSQL so every API replica counts the same.

``take`` counts one action or refuses it. One transaction under an advisory lock per account and
action: requests at the same moment queue for it instead of all seeing the same count and
slipping past together. Every time is the database's clock: clock_timestamp(), not now(), which
is when the caller's transaction began.
"""

from uuid import UUID

import psycopg

_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
_FORGET = (
    "DELETE FROM rate_event WHERE account_id = %s AND action = %s"
    " AND at <= clock_timestamp() - interval '1 minute'"
)
# how many were taken in the minute, and in how many seconds the oldest of them frees its place
_COUNT = (
    "SELECT count(*), ceil(extract(epoch FROM min(at) + interval '1 minute' - clock_timestamp()))"
    " FROM rate_event WHERE account_id = %s AND action = %s"
)
_NOTE = "INSERT INTO rate_event (account_id, action, at) VALUES (%s, %s, clock_timestamp())"


class RateLimited(Exception):
    """The account used its actions of this kind for the minute; ``retry_after_s`` until one frees."""

    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"try again in {retry_after_s} s")
        self.retry_after_s = retry_after_s


async def take(
    connection: psycopg.AsyncConnection, account_id: UUID, action: str, *, per_minute: int
) -> None:
    """Count one ``action`` of the account, or raise RateLimited when it took ``per_minute`` in
    the last minute. Inside a caller's transaction the lock holds until that one ends."""
    key = (account_id, action)
    async with connection.transaction():
        await connection.execute(_LOCK, (f"rate:{account_id}:{action}",))
        await connection.execute(_FORGET, key)
        cursor = await connection.execute(_COUNT, key)
        found = await cursor.fetchone()
        assert found is not None  # noqa: S101 - an aggregate always has its row
        taken, frees_in = found
        if taken >= per_minute:
            raise RateLimited(max(1, int(frees_in or 1)))
        await connection.execute(_NOTE, key)
