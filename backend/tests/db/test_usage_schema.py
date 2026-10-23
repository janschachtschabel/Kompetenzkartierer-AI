"""The accounting's tables (migration usage, plan M1 5.4, Festlegungen "Kosten"): what an account
may spend, what each model request cost, and what is held for the requests yet to be answered."""

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg import errors

from app.core.ids import new_id
from app.db.migrate import migrate

pytestmark = pytest.mark.pg


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        yield opened


def add_account(connection: psycopg.Connection) -> UUID:
    account = new_id()
    connection.execute(
        "INSERT INTO account (id, name) VALUES (%s, %s)", (account, f"konto-{account.hex[-12:]}")
    )
    return account


def add_job(connection: psycopg.Connection, account: UUID) -> UUID:
    job = new_id()
    connection.execute("INSERT INTO job_lane (lane) VALUES (%s) ON CONFLICT DO NOTHING", (str(account),))
    connection.execute(
        "INSERT INTO job (id, kind, lane) VALUES (%s, 'extraction.x1', %s)", (job, str(account))
    )
    return job


def insert(connection: psycopg.Connection, table: str, values: dict[str, Any]) -> int:
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    row = connection.execute(
        f"INSERT INTO {table} ({names}) VALUES ({marks}) RETURNING id",  # noqa: S608 - the test's own names
        tuple(values.values()),
    ).fetchone()
    assert row is not None
    return int(row[0])


def add_usage(connection: psycopg.Connection, account: UUID, **columns: Any) -> int:
    values = {
        "account_id": account,
        "purpose": "x1",
        "model": "gpt-6-luna",
        "input_tokens": 1_200,
        "cached_input_tokens": 1_000,
        "output_tokens": 300,
        "requests": 1,
        "unanswered_requests": 0,
        "estimated": False,
        **columns,
    }
    return insert(connection, "llm_usage", values)


def add_reservation(connection: psycopg.Connection, account: UUID, job: UUID, **columns: Any) -> int:
    values = {
        "account_id": account,
        "job_id": job,
        "purpose": "x1",
        "model": "gpt-6-luna",
        "input_tokens": 1_320,
        "output_tokens": 16_000,
        **columns,
    }
    return insert(connection, "usage_reservation", values)


def test_an_account_s_limits_are_counts_or_none(connection: psycopg.Connection) -> None:
    # NULL: no limit; tokens beyond what an integer holds
    unlimited, limited = add_account(connection), add_account(connection)
    connection.execute("INSERT INTO quota (account_id) VALUES (%s)", (unlimited,))
    connection.execute(
        "INSERT INTO quota (account_id, token_limit, page_limit) VALUES (%s, %s, 0)", (limited, 5 * 10**9)
    )

    rows = connection.execute(
        "SELECT account_id, token_limit, page_limit FROM quota ORDER BY account_id"
    ).fetchall()

    assert rows == [(unlimited, None, None), (limited, 5 * 10**9, 0)]


@pytest.mark.parametrize("column", ["token_limit", "page_limit"])
def test_a_limit_below_nothing_is_refused(connection: psycopg.Connection, column: str) -> None:
    account = add_account(connection)

    with pytest.raises(errors.CheckViolation):
        connection.execute(
            f"INSERT INTO quota (account_id, {column}) VALUES (%s, -1)",  # noqa: S608 - the test's names
            (account,),
        )


def test_an_account_has_one_quota_and_takes_it_along(connection: psycopg.Connection) -> None:
    account = add_account(connection)
    connection.execute("INSERT INTO quota (account_id, token_limit) VALUES (%s, 10)", (account,))

    with pytest.raises(errors.UniqueViolation):
        connection.execute("INSERT INTO quota (account_id, token_limit) VALUES (%s, 20)", (account,))
    connection.execute("DELETE FROM account WHERE id = %s", (account,))

    assert connection.execute("SELECT count(*) FROM quota").fetchone() == (0,)


def test_a_request_s_cost_is_kept_with_its_job_run_and_purpose(connection: psycopg.Connection) -> None:
    account = add_account(connection)
    job, run = add_job(connection, account), new_id()

    usage = add_usage(connection, account, job_id=job, run_id=run)

    row = connection.execute(
        "SELECT account_id, job_id, run_id, purpose, model, input_tokens, cached_input_tokens, output_tokens,"
        " requests, unanswered_requests, estimated, booked_at IS NOT NULL FROM llm_usage WHERE id = %s",
        (usage,),
    ).fetchone()
    assert row == (account, job, run, "x1", "gpt-6-luna", 1_200, 1_000, 300, 1, 0, False, True)


@pytest.mark.parametrize(
    "column", ["input_tokens", "cached_input_tokens", "output_tokens", "requests", "unanswered_requests"]
)
def test_a_count_below_nothing_is_refused(connection: psycopg.Connection, column: str) -> None:
    account = add_account(connection)

    with pytest.raises(errors.CheckViolation):
        add_usage(connection, account, **{column: -1})


def test_more_input_from_the_cache_than_input_is_refused(connection: psycopg.Connection) -> None:
    account = add_account(connection)

    add_usage(connection, account, input_tokens=500, cached_input_tokens=500)
    with pytest.raises(errors.CheckViolation):
        add_usage(connection, account, input_tokens=500, cached_input_tokens=501)


def test_a_cost_says_whether_it_was_estimated(connection: psycopg.Connection) -> None:
    # the writer says it: a reservation booked for a request nobody answered is not a count
    account = add_account(connection)

    with pytest.raises(errors.NotNullViolation):
        connection.execute(
            "INSERT INTO llm_usage (account_id, purpose, model, input_tokens, cached_input_tokens,"
            " output_tokens, requests, unanswered_requests)"
            " VALUES (%s, 'x1', 'gpt-6-luna', 1, 0, 1, 1, 0)",
            (account,),
        )
    estimated = add_usage(connection, account, requests=0, unanswered_requests=1, estimated=True)

    flag = connection.execute("SELECT estimated FROM llm_usage WHERE id = %s", (estimated,)).fetchone()
    assert flag == (True,)


@pytest.mark.parametrize(
    ("column", "value"),
    [("purpose", ""), ("purpose", "X1"), ("purpose", "x1 x2"), ("model", ""), ("model", "m" * 201)],
    ids=["empty-purpose", "upper-purpose", "spaced-purpose", "empty-model", "long-model"],
)
def test_a_cost_names_its_purpose_and_model_plainly(
    connection: psycopg.Connection, column: str, value: str
) -> None:
    account = add_account(connection)

    with pytest.raises(errors.CheckViolation):
        add_usage(connection, account, **{column: value})
    with pytest.raises(errors.CheckViolation):
        add_reservation(connection, account, add_job(connection, account), **{column: value})


def test_a_cost_is_charged_to_an_account_that_keeps_it(connection: psycopg.Connection) -> None:
    account = add_account(connection)
    add_usage(connection, account)

    with pytest.raises(errors.ForeignKeyViolation):
        add_usage(connection, new_id())
    with pytest.raises(errors.ForeignKeyViolation):  # what it spent stays on record
        connection.execute("DELETE FROM account WHERE id = %s", (account,))


def test_a_cost_outlives_its_job(connection: psycopg.Connection) -> None:
    # like the audit log: a record of what was spent, whatever becomes of the job and its run
    account = add_account(connection)
    job = add_job(connection, account)
    add_usage(connection, account, job_id=job, run_id=new_id())

    connection.execute("DELETE FROM job WHERE id = %s", (job,))

    assert connection.execute("SELECT job_id FROM llm_usage").fetchall() == [(job,)]


def test_a_reservation_holds_input_and_output_for_a_job_of_an_account(connection: psycopg.Connection) -> None:
    account = add_account(connection)
    job, run = add_job(connection, account), new_id()

    reservation = add_reservation(connection, account, job, run_id=run)

    row = connection.execute(
        "SELECT account_id, job_id, run_id, purpose, model, input_tokens, output_tokens,"
        " created_at IS NOT NULL FROM usage_reservation WHERE id = %s",
        (reservation,),
    ).fetchone()
    assert row == (account, job, run, "x1", "gpt-6-luna", 1_320, 16_000, True)


@pytest.mark.parametrize("column", ["input_tokens", "output_tokens"])
def test_a_reservation_holds_something(connection: psycopg.Connection, column: str) -> None:
    account = add_account(connection)
    job = add_job(connection, account)

    with pytest.raises(errors.CheckViolation):
        add_reservation(connection, account, job, **{column: 0})


@pytest.mark.parametrize("column", ["account_id", "job_id"])
def test_a_reservation_names_its_job_and_account(connection: psycopg.Connection, column: str) -> None:
    account = add_account(connection)
    job = add_job(connection, account)

    with pytest.raises(errors.NotNullViolation):
        add_reservation(connection, account, job, **{column: None})
    with pytest.raises(errors.ForeignKeyViolation):
        add_reservation(connection, account, job, **{column: new_id()})


def test_a_job_or_account_holding_a_reservation_stays_until_it_is_booked(
    connection: psycopg.Connection,
) -> None:
    # an open reservation is booked as spent (app/usage/ledger.py), never let go with its job
    account = add_account(connection)
    job = add_job(connection, account)
    add_reservation(connection, account, job)

    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute("DELETE FROM job WHERE id = %s", (job,))
    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute("DELETE FROM account WHERE id = %s", (account,))


# An index whose first key column is the column: the ledger sums an account's costs and
# reservations for each request it reserves, and books an abandoned job's reservations
_LEADING = """
SELECT EXISTS (
    SELECT FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
    WHERE i.indrelid = %s::regclass AND a.attname = %s
)
"""


@pytest.mark.parametrize(
    ("table", "column"),
    [("llm_usage", "account_id"), ("usage_reservation", "account_id"), ("usage_reservation", "job_id")],
)
def test_the_ledger_finds_its_rows_by_an_index(
    connection: psycopg.Connection, table: str, column: str
) -> None:
    assert connection.execute(_LEADING, (table, column)).fetchone() == (True,)
