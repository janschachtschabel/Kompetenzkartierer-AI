"""A stage's run says how it ended (migration extraction_run_outcome, plan M1 6.6): the attempt of its
job, its outcome once it ended - and only then - and what it made, as the stage after it needs it."""

from collections.abc import Iterator
from typing import Any, get_args

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from app.db.migrate import migrate
from app.db.runs import RunOutcome
from tests.db.l1 import CV, add_conversion, add_document, add_entity, listed_values, seed_vocabulary

pytestmark = pytest.mark.pg


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        seed_vocabulary(opened)
        yield opened


@pytest.fixture
def document(connection: psycopg.Connection) -> Any:
    return add_document(connection, add_conversion(connection))


def add_run(connection: psycopg.Connection, document: Any, **columns: Any) -> None:
    values = {"document_id": document, "stage_scheme": CV + "Stages", "stage_iri": CV + "stage_X1"} | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO extraction_run (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the test's own names
        (add_entity(connection, "extraction_run"), *values.values()),
    )


def test_the_database_lists_exactly_the_outcomes_the_code_knows(connection: psycopg.Connection) -> None:
    assert listed_values(connection, "extraction_run", "outcome") == set(get_args(RunOutcome))


def test_a_run_ends_with_its_outcome_and_what_it_made(connection: psycopg.Connection, document: Any) -> None:
    add_run(connection, document, attempt=1)
    add_run(
        connection,
        document,
        attempt=2,
        outcome="done",
        finished_at="2026-10-24T12:00:00Z",
        result=Jsonb({"units": [{"key": "E1"}]}),
    )

    rows = connection.execute(
        "SELECT attempt, outcome, result FROM extraction_run ORDER BY attempt"
    ).fetchall()

    assert rows == [(1, None, None), (2, "done", {"units": [{"key": "E1"}]})]


@pytest.mark.parametrize(
    "columns",
    [
        {"outcome": "done"},  # an outcome before the end
        {"finished_at": "2026-10-24T12:00:00Z"},  # an end without its outcome
        {"outcome": "aborted", "finished_at": "2026-10-24T12:00:00Z"},
        {"attempt": 0},
        {"result": Jsonb([1, 2])},
    ],
    ids=["outcome-unended", "ended-without-outcome", "unknown-outcome", "attempt-zero", "result-no-object"],
)
def test_a_run_s_end_is_whole_or_refused(
    connection: psycopg.Connection, document: Any, columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_run(connection, document, **columns)
