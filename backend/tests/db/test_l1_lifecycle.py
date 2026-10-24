"""What a document holds goes with it, and what a run made outlives the run (migrations l1_*):
the first layer's rows are taken away with their document, never left behind."""

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import migrate
from tests.db.l1 import (
    CV,
    add_conversion,
    add_document,
    add_entity,
    add_node,
    add_run,
    add_specification,
    add_statement,
    add_variant,
    seed_vocabulary,
)

pytestmark = pytest.mark.pg

TABLES = (
    "node",
    "statement",
    "statement_addressee",
    "anchor",
    "anchor_block",
    "extraction_run",
    "validation_finding",
    "specification",
    "variant",
    "document_profile",
)


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        seed_vocabulary(opened)
        yield opened


@pytest.fixture
def made(connection: psycopg.Connection) -> dict[str, Any]:
    made = add_conversion(connection)
    made["document"] = add_document(connection, made)
    return made


def counts(connection: psycopg.Connection) -> dict[str, int]:
    found = {}
    for table in TABLES:
        row = connection.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608 - our table names
        assert row is not None
        found[table] = row[0]
    return found


def fill(connection: psycopg.Connection, made: dict[str, Any]) -> dict[str, uuid.UUID]:
    """A run, a node and a statement it made, an anchor at a block, and a finding of the run."""
    document = made["document"]
    run = add_run(connection, document)
    node = add_node(connection, document, run_id=run)
    statement = add_statement(connection, document, node, run_id=run)
    anchor = add_entity(connection, "anchor")
    connection.execute(
        "INSERT INTO anchor (id, document_id, conversion_id, node_id, page_start) VALUES (%s, %s, %s, %s, 1)",
        (anchor, document, made["conversion"], node),
    )
    connection.execute(
        "INSERT INTO anchor_block (anchor_id, conversion_id, block_id) VALUES (%s, %s, 'p1-b1')",
        (anchor, made["conversion"]),
    )
    connection.execute(
        "INSERT INTO validation_finding (id, document_id, run_id, rule, severity, focus_id, message)"
        " VALUES (gen_random_uuid(), %s, %s, 'rule', 'warning', %s, 'Hinweis')",
        (document, run, statement),
    )
    connection.execute("INSERT INTO document_profile (document_id) VALUES (%s)", (document,))
    specification = add_specification(connection, document)
    variant = add_variant(connection, specification)
    connection.execute(
        "UPDATE node SET applies_to = ARRAY[%s, %s]::uuid[] WHERE id = %s", (specification, variant, node)
    )
    return {"run": run, "node": node, "statement": statement}


def test_a_document_taken_away_takes_all_it_holds(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    fill(connection, made)

    connection.execute("DELETE FROM document WHERE id = %s", (made["document"],))

    assert counts(connection) == dict.fromkeys(TABLES, 0)


def test_a_run_taken_away_leaves_what_it_made_without_it(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    filled = fill(connection, made)

    connection.execute("DELETE FROM extraction_run WHERE id = %s", (filled["run"],))

    left = connection.execute(
        "SELECT (SELECT run_id FROM node WHERE id = %s), (SELECT run_id FROM statement WHERE id = %s),"
        " (SELECT count(*) FROM validation_finding)",
        (filled["node"], filled["statement"]),
    ).fetchone()
    assert left == (None, None, 0)  # its findings were the run's


def test_what_a_run_made_or_found_is_of_the_run_s_document(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    other = add_document(connection, add_conversion(connection, b"\x02" * 32))
    foreign = add_run(connection, other)
    document = made["document"]

    with pytest.raises(errors.ForeignKeyViolation):
        add_node(connection, document, run_id=foreign)
    node = add_node(connection, document)
    with pytest.raises(errors.ForeignKeyViolation):
        add_statement(connection, document, node, run_id=foreign)
    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute(
            "INSERT INTO frame_part (id, document_id, part_kind, content, origin_scheme, origin_iri,"
            " review_status_scheme, review_status_iri, run_id, position)"
            " VALUES (%s, %s, 'operators', '{}', %s, %s, %s, %s, %s, 1)",
            (
                add_entity(connection, "frame_part"),
                document,
                CV + "Origins",
                CV + "orig_model",
                CV + "ReviewStatuses",
                CV + "rev_proposed",
                foreign,
            ),
        )
    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute(
            "INSERT INTO validation_finding (id, document_id, run_id, rule, severity, focus_id, message)"
            " VALUES (gen_random_uuid(), %s, %s, 'rule', 'warning', %s, 'Hinweis')",
            (document, foreign, node),
        )


# A foreign key's index: one whose key columns lead with all its columns, or with one of them that
# is not the document's - "(document_id, id)" finds a document's rows, not those of one run or
# node. A partial index counts: the layer's leave out the rows whose column is NULL alone
_UNINDEXED = """
SELECT c.conrelid::regclass::text, c.conname FROM pg_constraint c
WHERE c.contype = 'f' AND c.confdeltype IN ('c', 'n') AND NOT EXISTS (
    SELECT FROM pg_index i,
        LATERAL (SELECT (i.indkey::int2[])[0:least(cardinality(c.conkey), i.indnkeyatts) - 1] AS lead) AS l
    WHERE i.indrelid = c.conrelid AND (
        (l.lead @> c.conkey AND l.lead <@ c.conkey)
        OR i.indkey[0] IN (
            SELECT a.attnum FROM pg_attribute a
            WHERE a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) AND a.attname <> 'document_id'
        )
    )
)
ORDER BY 1, 2
"""


def test_what_goes_with_a_row_taken_away_is_found_by_an_index(connection: psycopg.Connection) -> None:
    # a cascade without one reads its whole table for each row taken away: a document's anchors
    assert connection.execute(_UNINDEXED).fetchall() == []


def test_a_run_s_stage_comes_from_the_core(connection: psycopg.Connection, made: dict[str, Any]) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        add_run(connection, made["document"], stage="sec_school")
    with pytest.raises(errors.ForeignKeyViolation):
        connection.execute(
            "INSERT INTO extraction_run (id, document_id, job_id, stage_scheme, stage_iri)"
            " VALUES (%s, %s, %s, %s, %s)",
            (
                add_entity(connection, "extraction_run"),
                made["document"],
                uuid.uuid4(),
                CV + "Stages",
                CV + "stage_X1",
            ),
        )
