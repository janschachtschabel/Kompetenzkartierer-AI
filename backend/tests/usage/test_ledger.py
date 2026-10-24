"""The ledger (plan M1 5.5, Festlegungen "Kosten"): a request's tokens are held from its account's
budget before it is sent and booked after it, in the reservation's place; what is left is the
limit less both, and requests side by side never hold more than it."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from uuid import UUID

import psycopg
import pytest
from prometheus_client import REGISTRY
from psycopg import errors
from psycopg.pq import TransactionStatus

from app.core.ids import new_id
from app.db.accounts import create_account
from app.db.migrate import migrate
from app.jobs.queue import account_lane, claim, complete, enqueue
from app.llm.metering import BudgetExhausted, Spent
from app.usage.ledger import Charge, Usage, book, book_abandoned, book_left_behind, reserve, usage_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


async def an_account(connection: psycopg.AsyncConnection, token_limit: int | None = 0) -> UUID:
    """An account with a quota of ``token_limit`` (None: no limit)."""
    account = await create_account(connection, f"konto-{new_id().hex[-12:]}", ["nutzer"])
    await connection.execute(
        "INSERT INTO quota (account_id, token_limit) VALUES (%s, %s)", (account, token_limit)
    )
    return account


async def a_charge(connection: psycopg.AsyncConnection, account: UUID, run_id: UUID | None = None) -> Charge:
    job = await enqueue(connection, "extraction.x1", account_lane(account))
    return Charge(account_id=account, job_id=job, purpose="x1", model="gpt-6-luna", run_id=run_id)


async def test_an_account_without_a_quota_may_spend_nothing(connection: psycopg.AsyncConnection) -> None:
    account = await create_account(connection, "ohne-quote", ["admin"])  # an admin's too
    charge = await a_charge(connection, account)

    with pytest.raises(BudgetExhausted):
        await reserve(connection, charge, input_tokens=1, output_tokens=1)

    assert await usage_of(connection, account) == Usage(
        token_limit=0, tokens_spent=0, tokens_held=0, tokens_estimated=0, page_limit=0, pages_spent=0
    )


async def test_an_account_without_a_limit_reserves_whatever_it_asks(
    connection: psycopg.AsyncConnection,
) -> None:
    account = await an_account(connection, token_limit=None)
    charge = await a_charge(connection, account)

    await reserve(connection, charge, input_tokens=10**9, output_tokens=10**9)

    usage = await usage_of(connection, account)
    assert (usage.token_limit, usage.tokens_held, usage.tokens_left) == (None, 2 * 10**9, None)


async def test_a_reservation_is_held_until_its_booking_takes_its_place(
    connection: psycopg.AsyncConnection,
) -> None:
    account = await an_account(connection, token_limit=1_000)
    run = new_id()
    charge = await a_charge(connection, account, run_id=run)

    reservation = await reserve(connection, charge, input_tokens=300, output_tokens=200)
    held = await usage_of(connection, account)
    booked = await book(
        connection,
        reservation,
        Spent(input_tokens=250, cached_input_tokens=100, output_tokens=50, requests=1),
    )

    assert (held.tokens_held, held.tokens_left) == (500, 500)
    assert booked is True
    after = await usage_of(connection, account)
    assert (after.tokens_held, after.tokens_spent, after.tokens_left) == (0, 300, 700)
    cursor = await connection.execute(
        "SELECT job_id, run_id, purpose, model, input_tokens, cached_input_tokens, output_tokens, requests,"
        " unanswered_requests, estimated FROM llm_usage WHERE account_id = %s",
        (account,),
    )
    assert await cursor.fetchall() == [(charge.job_id, run, "x1", "gpt-6-luna", 250, 100, 50, 1, 0, False)]


async def test_a_request_beyond_what_is_left_is_refused_and_one_up_to_it_is_not(
    connection: psycopg.AsyncConnection,
) -> None:
    account = await an_account(connection, token_limit=1_000)
    charge = await a_charge(connection, account)
    await book(
        connection, await reserve(connection, charge, 400, 200), Spent(input_tokens=400, output_tokens=200)
    )

    with pytest.raises(BudgetExhausted, match="400"):  # what is left, for the job's error
        await reserve(connection, charge, input_tokens=300, output_tokens=101)
    await reserve(connection, charge, input_tokens=300, output_tokens=100)

    assert (await usage_of(connection, account)).tokens_left == 0


async def test_a_booking_beyond_its_reservation_is_booked_all_the_same(
    connection: psycopg.AsyncConnection,
) -> None:
    # a gateway's model counts with its own tokenizer: what it charged is what was spent
    account = await an_account(connection, token_limit=1_000)
    charge = await a_charge(connection, account)
    reservation = await reserve(connection, charge, input_tokens=600, output_tokens=300)

    await book(connection, reservation, Spent(input_tokens=1_000, output_tokens=200, requests=1))

    usage = await usage_of(connection, account)
    assert (usage.tokens_spent, usage.tokens_left) == (1_200, 0)
    with pytest.raises(BudgetExhausted):
        await reserve(connection, charge, input_tokens=1, output_tokens=1)


async def test_a_reservation_is_booked_once(connection: psycopg.AsyncConnection) -> None:
    account = await an_account(connection, token_limit=1_000)
    charge = await a_charge(connection, account)
    reservation = await reserve(connection, charge, input_tokens=10, output_tokens=10)
    spent = Spent(input_tokens=5, output_tokens=5, requests=1)

    first, again = await book(connection, reservation, spent), await book(connection, reservation, spent)

    assert (first, again) == (True, False)
    assert (await usage_of(connection, account)).tokens_spent == 10


async def test_a_request_never_sent_is_booked_as_nothing(connection: psycopg.AsyncConnection) -> None:
    account = await an_account(connection, token_limit=1_000)
    charge = await a_charge(connection, account)
    reservation = await reserve(connection, charge, input_tokens=10, output_tokens=10)

    assert await book(connection, reservation, Spent()) is True

    cursor = await connection.execute("SELECT count(*) FROM llm_usage")
    assert await cursor.fetchone() == (0,)
    assert (await usage_of(connection, account)).tokens_left == 1_000


async def test_an_abandoned_job_s_reservations_are_booked_as_spent_and_estimated(
    connection: psycopg.AsyncConnection,
) -> None:
    # the provider may have charged for what was sent: held, it is spent, never let go
    account = await an_account(connection, token_limit=10_000)
    run = new_id()
    abandoned, other = await a_charge(connection, account, run_id=run), await a_charge(connection, account)
    await reserve(connection, abandoned, input_tokens=300, output_tokens=200)
    await reserve(connection, abandoned, input_tokens=400, output_tokens=200)
    answered = await reserve(connection, other, input_tokens=50, output_tokens=50)
    await book(connection, answered, Spent(input_tokens=40, output_tokens=10, requests=1))
    await reserve(connection, other, input_tokens=50, output_tokens=50)

    taken = await book_abandoned(connection, abandoned.job_id)

    assert taken == 2
    cursor = await connection.execute(
        "SELECT job_id, run_id, purpose, model, input_tokens, cached_input_tokens, output_tokens, requests,"
        " unanswered_requests, estimated FROM llm_usage WHERE estimated ORDER BY input_tokens"
    )
    assert await cursor.fetchall() == [
        (abandoned.job_id, run, "x1", "gpt-6-luna", 300, 0, 200, 0, 1, True),
        (abandoned.job_id, run, "x1", "gpt-6-luna", 400, 0, 200, 0, 1, True),
    ]
    usage = await usage_of(connection, account)
    assert (usage.tokens_spent, usage.tokens_estimated, usage.tokens_held) == (1_150, 1_100, 100)
    assert await book_abandoned(connection, abandoned.job_id) == 0


async def test_a_reservation_booked_as_abandoned_is_booked_no_more(
    connection: psycopg.AsyncConnection,
) -> None:
    # a worker that lost its job's lease answers late: what was booked for it stands
    account = await an_account(connection, token_limit=1_000)
    charge = await a_charge(connection, account)
    reservation = await reserve(connection, charge, input_tokens=100, output_tokens=100)
    await book_abandoned(connection, charge.job_id)

    assert await book(connection, reservation, Spent(input_tokens=90, output_tokens=10, requests=1)) is False

    usage = await usage_of(connection, account)
    assert (usage.tokens_spent, usage.tokens_estimated) == (200, 200)


async def test_billable_pages_count_against_the_page_limit(connection: psycopg.AsyncConnection) -> None:
    # nothing holds to the page limit yet: no engine that costs is offered (plan M1 5.4)
    account = await an_account(connection, token_limit=0)
    await connection.execute("UPDATE quota SET page_limit = 50 WHERE account_id = %s", (account,))
    for pages, billable in ((7, True), (30, False), (5, True)):
        await a_conversion_booked(connection, account, pages, billable=billable)

    usage = await usage_of(connection, account)

    assert (usage.page_limit, usage.pages_spent) == (50, 12)


async def a_conversion_booked(
    connection: psycopg.AsyncConnection, account: UUID, pages: int, *, billable: bool
) -> None:
    file_id, conversion = new_id(), new_id()
    await connection.execute(
        "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 1, %s)",
        (file_id, file_id.bytes * 2, f"sources/{file_id.hex}"),
    )
    await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'conversion')", (conversion,))
    await connection.execute(
        "INSERT INTO conversion (id, source_file_id, engine) VALUES (%s, %s, 'pdfplumber')",
        (conversion, file_id),
    )
    await connection.execute(
        "INSERT INTO conversion_usage (conversion_id, account_id, engine, pages, billable)"
        " VALUES (%s, %s, 'pdfplumber', %s, %s)",
        (conversion, account, pages, billable),
    )


async def test_reserving_under_another_isolation_is_refused(database_url: str) -> None:
    # repeatable read sums what was there when it began: another's reservation would slip past
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as setup:
        charge = await a_charge(setup, await an_account(setup, token_limit=1_000))
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.set_isolation_level(psycopg.IsolationLevel.REPEATABLE_READ)

        with pytest.raises(errors.InvalidTransactionState, match="read committed"):
            await reserve(connection, charge, input_tokens=1, output_tokens=1)


async def test_reservations_side_by_side_never_hold_more_than_the_limit(database_url: str) -> None:
    # twenty connections, all open, ask at once for 100 each where 1,000 are left: ten hold
    migrate(database_url)
    async with AsyncExitStack() as opened:
        connections = [
            await opened.enter_async_context(
                await psycopg.AsyncConnection.connect(database_url, autocommit=True)
            )
            for _ in range(21)
        ]
        setup, side_by_side = connections[0], connections[1:]
        account = await an_account(setup, token_limit=1_000)
        charge = await a_charge(setup, account)

        asked = await asyncio.gather(
            *(reserve(own, charge, input_tokens=60, output_tokens=40) for own in side_by_side),
            return_exceptions=True,
        )

        assert (
            sorted(type(answer).__name__ for answer in asked)
            == ["BudgetExhausted"] * 10 + ["Reservation"] * 10
        )
        assert (await usage_of(setup, account)).tokens_held == 1_000


def reservations(outcome: str) -> float:
    return REGISTRY.get_sample_value("kka_usage_reservations_total", {"outcome": outcome}) or 0.0


async def test_reservations_are_counted_by_what_became_of_them(connection: psycopg.AsyncConnection) -> None:
    # held, refused for the budget, booked - or late, where it was booked as abandoned before
    outcomes = ("held", "refused", "booked", "late", "abandoned")
    before = {outcome: reservations(outcome) for outcome in outcomes}
    account = await an_account(connection, token_limit=1_000)
    answered, abandoned = await a_charge(connection, account), await a_charge(connection, account)
    booked = await reserve(connection, answered, input_tokens=100, output_tokens=100)
    await book(connection, booked, Spent(input_tokens=50, output_tokens=50, requests=1))
    late = await reserve(connection, abandoned, input_tokens=100, output_tokens=100)
    with pytest.raises(BudgetExhausted):
        await reserve(connection, abandoned, input_tokens=900, output_tokens=100)
    await book_abandoned(connection, abandoned.job_id)
    await book(connection, late, Spent(input_tokens=50, output_tokens=50, requests=1))

    assert {outcome: reservations(outcome) - before[outcome] for outcome in outcomes} == {
        "held": 2,
        "refused": 1,
        "booked": 1,
        "late": 1,
        "abandoned": 1,
    }


async def test_a_reservation_or_booking_inside_another_transaction_is_refused(database_url: str) -> None:
    # held to the caller's commit, its quota's lock would stop the account's every other request,
    # and a rollback after the request went out would take a paid reservation along
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as setup:
        charge = await a_charge(setup, await an_account(setup, token_limit=1_000))
        reservation = await reserve(setup, charge, input_tokens=10, output_tokens=10)
    async with await psycopg.AsyncConnection.connect(database_url) as connection:
        await connection.execute("SELECT 1")

        with pytest.raises(ValueError, match="transaction of its own"):
            await reserve(connection, charge, input_tokens=10, output_tokens=10)
        with pytest.raises(ValueError, match="transaction of its own"):
            await book(connection, reservation, Spent(input_tokens=5, output_tokens=5, requests=1))


async def test_a_booking_commits_on_a_connection_that_does_not(database_url: str) -> None:
    # a statement there opens a transaction the caller could still roll back, the booking with it
    migrate(database_url)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as setup:
        charge = await a_charge(setup, await an_account(setup, token_limit=1_000))
        reservation = await reserve(setup, charge, input_tokens=10, output_tokens=10)
        async with await psycopg.AsyncConnection.connect(database_url) as connection:
            await book(connection, reservation, Spent(input_tokens=5, output_tokens=5, requests=1))

            assert connection.info.transaction_status == TransactionStatus.IDLE
            cursor = await setup.execute("SELECT count(*) FROM llm_usage")
            assert await cursor.fetchone() == (1,)


async def test_a_booking_whose_commit_failed_is_counted_once_it_is_booked(
    connection: psycopg.AsyncConnection,
) -> None:
    # asked again after a failed commit, a booking counted before its commit would count twice
    account = await an_account(connection, token_limit=1_000)
    reservation = await reserve(
        connection, await a_charge(connection, account), input_tokens=10, output_tokens=10
    )
    await connection.execute(
        "CREATE FUNCTION refuse_usage() RETURNS trigger LANGUAGE plpgsql AS"
        " $$ BEGIN RAISE EXCEPTION 'refused at commit (invented)'; END $$"
    )
    await connection.execute(
        "CREATE CONSTRAINT TRIGGER refuse_at_commit AFTER INSERT ON llm_usage"
        " DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION refuse_usage()"
    )
    spent = Spent(input_tokens=5, output_tokens=5, requests=1)
    before = reservations("booked")

    with pytest.raises(errors.RaiseException, match="refused at commit"):
        await book(connection, reservation, spent)

    assert reservations("booked") == before
    assert (await usage_of(connection, account)).tokens_held == 20  # still held
    await connection.execute("DROP TRIGGER refuse_at_commit ON llm_usage")
    assert await book(connection, reservation, spent) is True
    assert reservations("booked") == before + 1


async def test_the_reservations_of_jobs_not_running_are_booked_as_abandoned_those_of_one_running_are_not(
    connection: psycopg.AsyncConnection,
) -> None:
    # a job handed back after its lease ran out, or ended by a cancel or a dead worker, holds no attempt
    account = await an_account(connection, token_limit=10_000)
    waiting, running, done = [await a_charge(connection, account) for _ in range(3)]
    for charge in (waiting, running, done):
        await reserve(connection, charge, input_tokens=100, output_tokens=100)
    claimed = []
    while (job := await claim(connection, "w1", ["extraction.x1"], 60)) is not None:
        claimed.append(job)
    await connection.execute("UPDATE job SET status = 'queued', lease_owner = NULL, lease_token = NULL,"
                             " lease_expires_at = NULL WHERE id = %s", (waiting.job_id,))  # fmt: skip
    await complete(connection, next(job for job in claimed if job.id == done.job_id), None)

    taken = await book_left_behind(connection)

    assert taken == 2
    cursor = await connection.execute("SELECT job_id FROM usage_reservation")
    assert await cursor.fetchall() == [(running.job_id,)]
    assert await book_left_behind(connection) == 0
