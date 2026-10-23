"""Whether an account may start a model job (plan M1 5.6, Festlegungen "Kosten"; after the old
app's MAX_JOBS_IN_FLIGHT).

``admit_model_job`` runs in the transaction that enqueues the job, under a lock per account held
to its end and read committed alone: starts side by side take turns, and each counts the jobs
the others enqueued. An account that spent its budget starts none - an admin's too, unless its
quota has no limit; what its calls in flight hold mostly comes back with their bookings, and the
start's first reservation decides on it. One with ``max_in_flight`` model jobs waiting or
running starts no more, and starts beyond the minute's limit wait. A start refused takes no
place in the minute.
"""

from collections.abc import Collection
from uuid import UUID

import psycopg
from psycopg.pq import TransactionStatus

from app.db.rate_limits import take
from app.jobs.queue import account_lane
from app.usage.ledger import usage_of

# The job kinds that call the model: none yet, X1 is the first (plan M1, Paket 6)
MODEL_JOB_KINDS: frozenset[str] = frozenset()
# The old app's answer to a client starting too many: come back in a minute
JOBS_RETRY_AFTER_S = 60
_READ_COMMITTED = "SELECT read_committed_alone('a model job''s admission')"
_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"
_IN_FLIGHT = (
    "SELECT count(*) FROM job WHERE lane = %s AND kind = ANY (%s) AND status IN ('queued', 'running')"
)


class NoBudget(Exception):
    """The account has spent the tokens it may."""


class TooManyJobs(Exception):
    """The account has as many model jobs waiting or running as it may."""

    def __init__(self, in_flight: int) -> None:
        super().__init__(f"{in_flight} model jobs waiting or running")
        self.retry_after_s = JOBS_RETRY_AFTER_S


async def admit_model_job(
    connection: psycopg.AsyncConnection,
    account_id: UUID,
    *,
    kinds: Collection[str],
    max_in_flight: int,
    starts_per_minute: int,
) -> None:
    """Admit a start of a model job of ``kinds`` - the job kinds that call the model - or raise
    NoBudget, TooManyJobs or RateLimited (app/db/rate_limits.py). ValueError outside a
    transaction: the lock would go before the job is enqueued."""
    if connection.info.transaction_status != TransactionStatus.INTRANS:
        raise ValueError("a model job is admitted in the transaction that enqueues it")
    await connection.execute(_READ_COMMITTED)
    await connection.execute(_LOCK, (f"admission:{account_id}",))
    usage = await usage_of(connection, account_id)
    if usage.token_limit is not None and usage.tokens_spent >= usage.token_limit:
        raise NoBudget("no tokens left")
    cursor = await connection.execute(_IN_FLIGHT, (account_lane(account_id), list(kinds)))
    row = await cursor.fetchone()
    assert row is not None  # noqa: S101 - an aggregate always has its row
    if row[0] >= max_in_flight:
        raise TooManyJobs(row[0])
    await take(connection, account_id, "model.start", per_minute=starts_per_minute)
