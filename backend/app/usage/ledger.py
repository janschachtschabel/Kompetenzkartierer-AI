"""The ledger of the model's work (plan M1 5.5, Festlegungen "Kosten"; tables in migration 0016).

Before a request is sent, ``reserve`` holds its tokens - its input as counted, its output up to
the cap - from its account's budget, in one transaction under the lock of the account's quota
row: requests side by side wait for each other, and each sums what the others booked and hold
once they are done. What is left is the limit less both, summed anew each time, so there is no
counter to drift from the rows. ``book`` puts what the answer reports in the reservation's place;
``book_abandoned`` books a job's open reservations as spent, estimated, since the provider may
have charged for what was sent. Either takes a reservation once, whichever comes first.

simplify: the sums read all of an account's rows for each request (one row a request, found by
an index); a running total kept beside them would serve, should accounts come to hold millions.
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.llm.metering import BudgetExhausted, Spent

_READ_COMMITTED = "SELECT read_committed_alone('a reservation')"
# No row is a limit of nothing; a row's NULL, no limit
_LIMIT = "SELECT token_limit FROM quota WHERE account_id = %s FOR UPDATE"
_TAKEN = """
    SELECT (SELECT coalesce(sum(input_tokens + output_tokens), 0) FROM llm_usage
            WHERE account_id = %(account)s)
        + (SELECT coalesce(sum(input_tokens + output_tokens), 0) FROM usage_reservation
            WHERE account_id = %(account)s)
"""
_HOLD = """
    INSERT INTO usage_reservation (account_id, job_id, run_id, purpose, model, input_tokens, output_tokens)
    VALUES (%(account)s, %(job)s, %(run)s, %(purpose)s, %(model)s, %(input)s, %(output)s)
    RETURNING id
"""
# One statement: the reservation goes and its cost comes together, or neither; a request never
# sent costs nothing and leaves no row
_BOOK = """
    WITH taken AS (
        DELETE FROM usage_reservation WHERE id = %(id)s RETURNING account_id, job_id, run_id, purpose, model
    ), booked AS (
        INSERT INTO llm_usage (account_id, job_id, run_id, purpose, model, input_tokens, cached_input_tokens,
            output_tokens, requests, unanswered_requests, estimated)
        SELECT account_id, job_id, run_id, purpose, model, %(input)s, %(cached)s, %(output)s, %(requests)s,
            %(unanswered)s, %(estimated)s
        FROM taken WHERE %(spent)s
    )
    SELECT count(*) FROM taken
"""
# Held, a request may have been sent: it counts as one nobody answered
_BOOK_ABANDONED = """
    WITH taken AS (
        DELETE FROM usage_reservation WHERE job_id = %s
        RETURNING account_id, job_id, run_id, purpose, model, input_tokens, output_tokens
    )
    INSERT INTO llm_usage (account_id, job_id, run_id, purpose, model, input_tokens, cached_input_tokens,
        output_tokens, requests, unanswered_requests, estimated)
    SELECT account_id, job_id, run_id, purpose, model, input_tokens, 0, output_tokens, 0, 1, true FROM taken
"""
_LIMITS = "SELECT token_limit, page_limit FROM quota WHERE account_id = %s"
_COUNTS = """
    SELECT spent.tokens, spent.estimated, held.tokens, pages.billable
    FROM (
        SELECT coalesce(sum(input_tokens + output_tokens), 0)::bigint AS tokens,
            coalesce(sum(input_tokens + output_tokens) FILTER (WHERE estimated), 0)::bigint AS estimated
        FROM llm_usage WHERE account_id = %(account)s
    ) AS spent, (
        SELECT coalesce(sum(input_tokens + output_tokens), 0)::bigint AS tokens
        FROM usage_reservation WHERE account_id = %(account)s
    ) AS held, (
        SELECT coalesce(sum(pages) FILTER (WHERE billable), 0)::bigint AS billable
        FROM conversion_usage WHERE account_id = %(account)s
    ) AS pages
"""


@dataclass(frozen=True)
class Charge:
    """Whom a request is charged to and what for: the account, the job that asks, its purpose
    (the stage, ``x4``) and the model; the run, where a stage of the pipeline asks."""

    account_id: UUID
    job_id: UUID
    purpose: str
    model: str
    run_id: UUID | None = None


@dataclass(frozen=True)
class Reservation:
    id: int


@dataclass(frozen=True)
class Usage:
    """An account's limits (None: no limit) and what it spent - of the tokens, ``tokens_estimated``
    booked as held for requests nobody answered - and holds for requests not yet answered."""

    token_limit: int | None
    tokens_spent: int
    tokens_held: int
    tokens_estimated: int
    page_limit: int | None
    pages_spent: int  # of engines that cost

    @property
    def tokens_left(self) -> int | None:
        """None for no limit; never below nothing, though an answer may cost more than was held."""
        if self.token_limit is None:
            return None
        return max(0, self.token_limit - self.tokens_spent - self.tokens_held)


async def reserve(
    connection: psycopg.AsyncConnection, charge: Charge, input_tokens: int, output_tokens: int
) -> Reservation:
    """Hold ``input_tokens`` and ``output_tokens`` for a request of ``charge``; BudgetExhausted
    where what is left of the account's budget does not hold both. Under read committed alone:
    repeatable read would sum what was there when its transaction began."""
    async with connection.transaction():
        await connection.execute(_READ_COMMITTED)
        cursor = await connection.execute(_LIMIT, (charge.account_id,))
        row = await cursor.fetchone()
        limit = 0 if row is None else row[0]
        if limit is not None:
            cursor = await connection.execute(_TAKEN, {"account": charge.account_id})
            taken = await cursor.fetchone()
            assert taken is not None  # noqa: S101 - an aggregate always has its row
            left = limit - int(taken[0])
            if input_tokens + output_tokens > left:
                raise BudgetExhausted(f"{input_tokens + output_tokens} tokens asked, {max(0, left)} left")
        cursor = await connection.execute(
            _HOLD,
            {
                "account": charge.account_id,
                "job": charge.job_id,
                "run": charge.run_id,
                "purpose": charge.purpose,
                "model": charge.model,
                "input": input_tokens,
                "output": output_tokens,
            },
        )
        held = await cursor.fetchone()
    assert held is not None  # noqa: S101 - an INSERT … RETURNING returns its row
    return Reservation(int(held[0]))


async def book(connection: psycopg.AsyncConnection, reservation: Reservation, spent: Spent) -> bool:
    """Book ``spent`` in the reservation's place; False where it was booked already (by
    ``book_abandoned``, for a job given up on), and nothing is booked again."""
    cursor = await connection.execute(
        _BOOK,
        {
            "id": reservation.id,
            "input": spent.input_tokens,
            "cached": spent.cached_input_tokens,
            "output": spent.output_tokens,
            "requests": spent.requests,
            "unanswered": spent.unanswered_requests,
            "estimated": spent.estimated,
            "spent": spent != Spent(),
        },
    )
    row = await cursor.fetchone()
    assert row is not None  # noqa: S101 - an aggregate always has its row
    return bool(row[0])


async def book_abandoned(connection: psycopg.AsyncConnection, job_id: UUID) -> int:
    """Book the job's open reservations as spent and estimated, each a request nobody answered;
    how many it took."""
    cursor = await connection.execute(_BOOK_ABANDONED, (job_id,))
    return cursor.rowcount


async def usage_of(connection: psycopg.AsyncConnection, account_id: UUID) -> Usage:
    """What the account may spend, spent and holds; without a quota row its limits are nothing."""
    cursor = await connection.execute(_LIMITS, (account_id,))
    limits = await cursor.fetchone()
    token_limit, page_limit = (0, 0) if limits is None else limits
    cursor = await connection.execute(_COUNTS, {"account": account_id})
    counts = await cursor.fetchone()
    assert counts is not None  # noqa: S101 - aggregates always have their row
    spent, estimated, held, pages = counts
    return Usage(token_limit, spent, held, estimated, page_limit, pages)
