"""The conversion's tables (migration 0011, plan M1, 3.5): a register file's conversion by an
engine, its blocks, and the pages it booked."""

import re
from collections.abc import Iterator
from typing import Any, get_args
from uuid import UUID

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from app.conversion.base import BlockKind, offered_engines
from app.core.ids import new_id
from app.db.conversions import ConversionStatus, FailureCode
from app.db.migrate import migrate

pytestmark = pytest.mark.pg


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        yield opened


def a_file(connection: psycopg.Connection) -> UUID:
    file_id = new_id()
    connection.execute(
        "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 4, %s)",
        (file_id, new_id().bytes * 2, f"sources/{file_id.hex}"),
    )
    return file_id


def add_conversion(connection: psycopg.Connection, file_id: UUID, **columns: Any) -> UUID:
    conversion_id = new_id()
    connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'conversion')", (conversion_id,))
    values = {"id": conversion_id, "source_file_id": file_id, "engine": "pdfplumber", **columns}
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO conversion ({names}) VALUES ({marks})",  # noqa: S608 - the test's own names
        tuple(values.values()),
    )
    return conversion_id


DONE: dict[str, Any] = {
    "status": "done",
    "engine_version": "0.11.10",
    "pages": 2,
    "printed_pages": Jsonb(["5", None]),
    "markdown": "<!-- p1-b1 -->\nLernfeld 1",
    "finished_at": "2026-10-23T10:00:00Z",
}


def add_block(connection: psycopg.Connection, conversion_id: UUID, **columns: Any) -> None:
    values = {
        "conversion_id": conversion_id,
        "block_id": "p1-b1",
        "page": 1,
        "seq": 1,
        "kind": "text",
        "text": "Lernfeld 1",
        "x0": 56,
        "top": 70,
        "x1": 300,
        "bottom": 82,
        "font_size": 11,
        "bold": False,
        "italic": False,
        **columns,
    }
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO document_block ({names}) VALUES ({marks})",  # noqa: S608 - the test's own names
        tuple(values.values()),
    )


def listed_values(connection: psycopg.Connection, table: str, column: str) -> set[str]:
    found = connection.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s",
        (table, f"{table}_{column}_check"),
    ).fetchone()
    assert found is not None, f"no CHECK on {table}.{column}"
    return set(re.findall(r"'([^']*)'::text", found[0]))


LISTS: list[tuple[str, str, set[str]]] = [
    ("conversion", "engine", set(offered_engines())),
    ("conversion", "status", set(get_args(ConversionStatus))),
    ("conversion", "error_code", set(get_args(FailureCode))),
    ("document_block", "kind", set(get_args(BlockKind))),
    ("conversion_usage", "engine", set(offered_engines())),
]


@pytest.mark.parametrize(("table", "column", "known"), LISTS, ids=[f"{t}.{c}" for t, c, _ in LISTS])
def test_the_database_lists_exactly_the_values_the_code_knows(
    connection: psycopg.Connection, table: str, column: str, known: set[str]
) -> None:
    assert listed_values(connection, table, column) == known


def test_a_conversion_is_an_entity_of_its_own_kind(connection: psycopg.Connection) -> None:
    file_id = a_file(connection)
    stray = new_id()

    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute(
            "INSERT INTO conversion (id, source_file_id, engine) VALUES (%s, %s, 'pdfplumber')",
            (stray, file_id),
        )


def test_a_file_is_converted_once_by_each_engine(connection: psycopg.Connection) -> None:
    file_id = a_file(connection)
    add_conversion(connection, file_id)

    with pytest.raises(errors.UniqueViolation):
        add_conversion(connection, file_id)


@pytest.mark.parametrize(
    "columns",
    [
        {"status": "failed"},  # a failure names its reason
        {"status": "pending", "error_code": "needs_ocr"},
        {"status": "failed", "error_code": "needs_ocr"},  # and when it ended
        {**DONE, "markdown": None},  # a conversion done holds its text
        {**DONE, "pages": None},
        {**DONE, "finished_at": None},
        {"finished_at": "2026-10-23T10:00:00Z"},  # pending has not ended
        {**DONE, "pages": 3},  # a printed number, or none, for each page
    ],
    ids=["failed-without-code", "pending-with-code", "failed-without-end", "done-without-markdown",
         "done-without-pages", "done-without-end", "pending-ended", "printed-pages-not-the-pages"],
)  # fmt: skip
def test_a_conversion_s_state_says_what_it_holds(
    connection: psycopg.Connection, columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_conversion(connection, a_file(connection), **columns)


def test_the_states_a_conversion_runs_through_are_kept(connection: psycopg.Connection) -> None:
    add_conversion(connection, a_file(connection))
    add_conversion(connection, a_file(connection), **DONE)
    add_conversion(
        connection,
        a_file(connection),
        status="failed",
        error_code="needs_ocr",
        finished_at="2026-10-23T10:00:00Z",
    )


def test_a_block_is_named_as_the_kern_names_it_and_only_a_table_holds_cells(
    connection: psycopg.Connection,
) -> None:
    conversion_id = add_conversion(connection, a_file(connection), **DONE)
    add_block(connection, conversion_id)
    cell = {"id": "T1:r1c1", "page": 1, "row": 1, "column": 1, "text": "Nr.", "header": True}
    add_block(
        connection, conversion_id, block_id="p1-b2", seq=2, kind="table", cells=Jsonb([cell]), font_size=None
    )

    for columns in (
        {"block_id": "p1-x3", "seq": 3},
        {"block_id": "p2-b3", "seq": 3},  # named for another page than it stands on
        {"block_id": "p1-b3", "seq": 3, "kind": "table"},
        {"block_id": "p1-b3", "seq": 3, "kind": "table", "cells": Jsonb([])},  # a table of no cell
        {"block_id": "p1-b3", "seq": 3, "cells": Jsonb([])},
        {"block_id": "p1-b3", "seq": 2},  # one block at each place of the reading order
    ):
        with pytest.raises((errors.CheckViolation, errors.UniqueViolation)):
            add_block(connection, conversion_id, **columns)


def test_a_conversion_books_its_pages_once(connection: psycopg.Connection) -> None:
    conversion_id = add_conversion(connection, a_file(connection), **DONE)
    booking = (
        "INSERT INTO conversion_usage (conversion_id, engine, pages, billable)"
        " VALUES (%s, 'pdfplumber', 2, false)"
    )
    connection.execute(booking, (conversion_id,))

    with pytest.raises(errors.UniqueViolation):
        connection.execute(booking, (conversion_id,))
