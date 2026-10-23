"""An account's limit per minute for an action, as the API answers it (app/db/rate_limits.py)."""

from uuid import UUID

import psycopg

from app.api.errors import Refusal
from app.db.rate_limits import RateLimited, take


async def within_limit(
    connection: psycopg.AsyncConnection, account_id: UUID, action: str, per_minute: int, code: str
) -> None:
    """Count the action against the account's limit, or answer 429 with when to try again."""
    try:
        await take(connection, account_id, action, per_minute=per_minute)
    except RateLimited as limited:
        retry = {"Retry-After": str(limited.retry_after_s)}
        raise Refusal(429, code, "Too many of these for now; try again later.", retry) from None
