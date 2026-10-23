"""An account's limits as the API answers them: per minute for an action (app/db/rate_limits.py),
and for a model job's start, its budget and its jobs in flight too (app/usage/admission.py)."""

from collections.abc import Collection
from uuid import UUID

import psycopg

from app.api.errors import Refusal
from app.core.settings import Settings
from app.db.rate_limits import RateLimited, take
from app.usage.admission import MODEL_JOB_KINDS, NoBudget, TooManyJobs, admit_model_job


async def within_limit(
    connection: psycopg.AsyncConnection, account_id: UUID, action: str, per_minute: int, code: str
) -> None:
    """Count the action against the account's limit, or answer 429 with when to try again."""
    try:
        await take(connection, account_id, action, per_minute=per_minute)
    except RateLimited as limited:
        raise _too_many(limited.retry_after_s, code) from None


async def admit_model_start(
    connection: psycopg.AsyncConnection,
    account_id: UUID,
    settings: Settings,
    *,
    kinds: Collection[str] = MODEL_JOB_KINDS,
) -> None:
    """Admit a model job's start in the transaction that enqueues it, or answer 403 no_budget,
    429 too_many_jobs or 429 too_many_starts, each with when to try again where it passes."""
    try:
        await admit_model_job(
            connection,
            account_id,
            kinds=kinds,
            max_in_flight=settings.max_jobs_in_flight,
            starts_per_minute=settings.model_starts_per_minute,
        )
    except NoBudget:
        raise Refusal(403, "no_budget", "This account has no tokens left for the language model.") from None
    except TooManyJobs as refused:
        raise _too_many(refused.retry_after_s, "too_many_jobs") from None
    except RateLimited as limited:
        raise _too_many(limited.retry_after_s, "too_many_starts") from None


def _too_many(retry_after_s: int, code: str) -> Refusal:
    retry = {"Retry-After": str(retry_after_s)}
    return Refusal(429, code, "Too many of these for now; try again later.", retry)
