"""A unit of X4 done (migration extraction_unit, plan M1 7b): once per document, by a run of that
document; what it found missing names docking points; its run or its node gone, it is open again."""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import migrate
from tests.db.l1 import CV, add_conversion, add_document, add_node, add_run, seed_vocabulary

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


def add_unit(
    connection: psycopg.Connection, document: Any, run: Any, key: str = "E1", **columns: Any
) -> None:
    values = {"document_id": document, "unit_key": key, "run_id": run, "statements": 0} | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO extraction_unit ({names}) VALUES ({marks})",  # noqa: S608 - the tests' own names
        tuple(values.values()),
    )


def units(connection: psycopg.Connection) -> list[tuple[Any, ...]]:
    return connection.execute("SELECT unit_key, statements FROM extraction_unit ORDER BY unit_key").fetchall()


def test_a_unit_is_done_once_per_document(connection: psycopg.Connection, document: Any) -> None:
    run, other_run = add_run(connection, document), add_run(connection, document)
    add_unit(connection, document, run, "E1", statements=3)

    with pytest.raises(errors.UniqueViolation):
        add_unit(connection, document, other_run, "E1")
    other = add_document(connection, add_conversion(connection, b"\x02" * 32))
    add_unit(connection, other, add_run(connection, other), "E1")  # another document's E1

    assert connection.execute("SELECT count(*) FROM extraction_unit").fetchone() == (2,)


@pytest.mark.parametrize("key", ["E0", "E1", "E123456"])
def test_a_unit_is_named_as_x2_names_its_packages(
    connection: psycopg.Connection, document: Any, key: str
) -> None:
    add_unit(connection, document, add_run(connection, document), key)

    assert units(connection) == [(key, 0)]


@pytest.mark.parametrize("key", ["", "E", "X1", "e1", "E1234567", "E1 "])
def test_anything_else_is_no_unit(connection: psycopg.Connection, document: Any, key: str) -> None:
    with pytest.raises(errors.CheckViolation):
        add_unit(connection, document, add_run(connection, document), key)


def test_a_unit_counts_no_fewer_than_no_statements(connection: psycopg.Connection, document: Any) -> None:
    with pytest.raises(errors.CheckViolation):
        add_unit(connection, document, add_run(connection, document), statements=-1)


def test_what_a_unit_found_missing_are_docking_points(connection: psycopg.Connection, document: Any) -> None:
    run = add_run(connection, document)
    add_unit(connection, document, run, "E1", checked_absent=[CV + "dock_level", CV + "dock_time"])

    with pytest.raises(errors.CheckViolation):
        add_unit(connection, document, run, "E2", checked_absent=[CV + "dock_level", CV + "mark_bold"])
    with pytest.raises(errors.CheckViolation):
        add_unit(connection, document, run, "E3", checked_absent=[None])


def test_a_unit_is_done_by_a_run_of_its_own_document(connection: psycopg.Connection, document: Any) -> None:
    other = add_document(connection, add_conversion(connection, b"\x02" * 32))

    with pytest.raises(errors.ForeignKeyViolation):
        add_unit(connection, document, add_run(connection, other))
    with pytest.raises(errors.ForeignKeyViolation):
        add_unit(connection, document, add_run(connection, document), node_id=add_node(connection, other))


def test_its_run_or_its_node_gone_a_unit_stays_done(connection: psycopg.Connection, document: Any) -> None:
    # what it wrote outlives its run (statement.run_id SET NULL), and its node the editors took away
    # themselves: asked again, it would meet its statements' positions or name a node gone
    run, node = add_run(connection, document), add_node(connection, document)
    add_unit(connection, document, run, "E1", node_id=node)

    connection.execute("DELETE FROM node WHERE id = %s", (node,))
    connection.execute("DELETE FROM extraction_run WHERE id = %s", (run,))

    assert connection.execute("SELECT unit_key, run_id, node_id FROM extraction_unit").fetchall() == [
        ("E1", None, None)
    ]


def test_what_a_unit_found_missing_stays_docking_points_when_changed(
    connection: psycopg.Connection, document: Any
) -> None:
    add_unit(connection, document, add_run(connection, document), "E1", checked_absent=[CV + "dock_level"])

    with pytest.raises(errors.CheckViolation):
        connection.execute("UPDATE extraction_unit SET checked_absent = ARRAY[%s]", (CV + "mark_bold",))
