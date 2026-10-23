"""The tables of where values were found and what X5 found of them (migration l1_anchors, plan M1
4.4): anchors at the blocks of their document's conversion, frame parts, findings."""

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from app.db.migrate import migrate
from app.domain.l1 import FramePartKind, Severity
from tests.db.l1 import (
    CV,
    add_conversion,
    add_document,
    add_entity,
    add_node,
    add_specification,
    add_statement,
    listed_values,
    seed_vocabulary,
)

pytestmark = pytest.mark.pg

SCHEMAS = Path(__file__).resolve().parents[3] / "ontology" / "schemas"


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
    made["node"] = add_node(connection, made["document"])
    return made


def add_anchor(connection: psycopg.Connection, made: dict[str, Any], **columns: Any) -> uuid.UUID:
    anchor = add_entity(connection, "anchor")
    values = {
        "document_id": made["document"],
        "conversion_id": made["conversion"],
        "node_id": made["node"],
        "page_start": 1,
    } | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO anchor (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the tests' own names
        (anchor, *values.values()),
    )
    return anchor


def add_block(connection: psycopg.Connection, anchor: uuid.UUID, conversion: uuid.UUID, block: str) -> None:
    connection.execute(
        "INSERT INTO anchor_block (anchor_id, conversion_id, block_id) VALUES (%s, %s, %s)",
        (anchor, conversion, block),
    )


def test_an_anchor_names_its_page_or_the_page_the_document_prints(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    add_anchor(connection, made, page_start=None, printed_page="IV")

    with pytest.raises(errors.CheckViolation):
        add_anchor(connection, made, page_start=None)


@pytest.mark.parametrize(
    "columns",
    [
        {"page_start": 0},
        {"page_start": 3, "page_end": 2},
        {"page_start": None, "printed_page": "IV", "page_end": 5},  # an end without its start
        {"page_start": None, "printed_page": " "},
        {"char_start": 5, "char_end": 4},
        {"char_end": -1},
        {"match_score": 1.5},
        {"table_cell": "r3c2"},
        {"match_kind_scheme": CV + "MatchKinds"},  # a scheme without its value
    ],
    ids=["page", "page-range", "page-end", "printed-page", "char-range", "char-end", "score", "cell", "pair"],
)
def test_an_anchor_s_values_keep_their_forms(
    connection: psycopg.Connection, made: dict[str, Any], columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_anchor(connection, made, **columns)


def test_an_anchor_anchors_one_thing_of_its_own_document(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    statement = add_statement(connection, made["document"], made["node"])
    other = add_conversion(connection, b"\x02" * 32)
    foreign_document = add_document(connection, other)
    foreign = add_node(connection, foreign_document)

    with pytest.raises(errors.CheckViolation):
        add_anchor(connection, made, statement_id=statement)  # beside the node
    with pytest.raises(errors.ForeignKeyViolation):
        add_anchor(connection, made, node_id=foreign)
    with pytest.raises(errors.ForeignKeyViolation):
        add_anchor(
            connection, made, node_id=None, statement_id=add_statement(connection, foreign_document, foreign)
        )
    with pytest.raises(errors.ForeignKeyViolation):
        add_anchor(connection, made, conversion_id=other["conversion"])


def test_an_anchor_may_stand_for_the_document_itself_or_one_of_its_specifications(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    # X1 anchors a document's title and dates, and what it stands for (x1-dokumentprofil.schema.json)
    specification = add_specification(connection, made["document"])
    other = add_document(connection, add_conversion(connection, b"\x02" * 32))
    foreign = add_specification(connection, other)

    add_anchor(connection, made, node_id=None)
    add_anchor(connection, made, node_id=None, specification_id=specification)

    with pytest.raises(errors.CheckViolation):
        add_anchor(connection, made, specification_id=specification)  # beside the node
    with pytest.raises(errors.ForeignKeyViolation):
        add_anchor(connection, made, node_id=None, specification_id=foreign)


def test_a_specification_taken_away_takes_its_anchors(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    specification = add_specification(connection, made["document"])
    add_anchor(connection, made, node_id=None, specification_id=specification)

    connection.execute("DELETE FROM specification WHERE id = %s", (specification,))

    assert connection.execute("SELECT count(*) FROM anchor").fetchone() == (0,)


def test_an_anchor_s_blocks_are_blocks_of_its_document_s_conversion(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    anchor = add_anchor(connection, made)
    add_block(connection, anchor, made["conversion"], "p1-b1")
    other = add_conversion(connection, b"\x02" * 32)

    with pytest.raises(errors.ForeignKeyViolation):
        add_block(connection, anchor, made["conversion"], "p9-b9")  # no such block
    with pytest.raises(errors.ForeignKeyViolation):
        add_block(
            connection, add_anchor(connection, made), other["conversion"], "p1-b1"
        )  # another conversion's
    with pytest.raises(errors.CheckViolation):
        add_block(connection, anchor, made["conversion"], "3-2")


def test_a_node_taken_away_takes_its_anchors_and_their_blocks(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    add_block(connection, add_anchor(connection, made), made["conversion"], "p1-b1")

    connection.execute("DELETE FROM node WHERE id = %s", (made["node"],))

    counts = connection.execute("SELECT (SELECT count(*) FROM anchor), (SELECT count(*) FROM anchor_block)")
    assert counts.fetchone() == (0, 0)


def add_frame_part(connection: psycopg.Connection, made: dict[str, Any], **columns: Any) -> uuid.UUID:
    part = add_entity(connection, "frame_part")
    values = {
        "document_id": made["document"],
        "part_kind": "operators",
        "content": Jsonb({"name": "Operatoren"}),
        "origin_scheme": CV + "Origins",
        "origin_iri": CV + "orig_model",
        "review_status_scheme": CV + "ReviewStatuses",
        "review_status_iri": CV + "rev_proposed",
    } | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO frame_part (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the tests' own names
        (part, *values.values()),
    )
    return part


def test_a_frame_part_is_anchored_like_a_node(connection: psycopg.Connection, made: dict[str, Any]) -> None:
    part = add_frame_part(connection, made)

    add_anchor(connection, made, node_id=None, frame_part_id=part)

    assert connection.execute("SELECT count(*) FROM anchor WHERE frame_part_id = %s", (part,)).fetchone() == (
        1,
    )
    connection.execute("DELETE FROM frame_part WHERE id = %s", (part,))
    assert connection.execute("SELECT count(*) FROM anchor").fetchone() == (0,)  # its anchors with it


def test_a_frame_part_s_kinds_are_the_parts_x3_names_beside_statements(
    connection: psycopg.Connection,
) -> None:
    schema = json.loads((SCHEMAS / "x3-rahmenteile.schema.json").read_text(encoding="utf-8"))
    named = set(schema["properties"]) - {"statements", "checkedAbsent"}

    assert listed_values(connection, "frame_part", "part_kind") == set(get_args(FramePartKind)) == named


def test_a_frame_part_s_content_is_an_object(connection: psycopg.Connection, made: dict[str, Any]) -> None:
    with pytest.raises(errors.CheckViolation):
        add_frame_part(connection, made, content=Jsonb(["Operatoren"]))


def test_a_frame_part_from_a_rule_names_the_rule(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    add_frame_part(connection, made, origin_iri=CV + "orig_rule", rule_id="legend-from-table")

    with pytest.raises(errors.CheckViolation):
        add_frame_part(connection, made, origin_iri=CV + "orig_rule")
    with pytest.raises(errors.CheckViolation):
        add_frame_part(connection, made, rule_id="legend-from-table")  # a rule named for a model's
    with pytest.raises(errors.CheckViolation):
        add_frame_part(connection, made, origin_iri=CV + "orig_rule", rule_id=" ")


def add_finding(connection: psycopg.Connection, made: dict[str, Any], **columns: Any) -> None:
    values = {
        "document_id": made["document"],
        "rule": "https://w3id.org/wlo/curriculum/shapes#StatementShape",
        "severity": "violation",
        "focus_id": made["node"],
        "message": "Eine Aussage braucht einen Adressaten.",
    } | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO validation_finding (id, {names}) VALUES (gen_random_uuid(), {marks})",  # noqa: S608
        tuple(values.values()),
    )


def test_a_finding_names_its_rule_severity_and_focus(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    add_finding(connection, made)
    add_finding(connection, made, focus_id=made["document"])  # about the document as a whole

    with pytest.raises(errors.NotNullViolation):
        add_finding(connection, made, focus_id=None)
    with pytest.raises(errors.ForeignKeyViolation):
        add_finding(connection, made, focus_id=uuid.uuid4())
    with pytest.raises(errors.CheckViolation):
        add_finding(connection, made, rule=" ")


def test_a_finding_s_severities_are_those_the_code_knows(connection: psycopg.Connection) -> None:
    assert listed_values(connection, "validation_finding", "severity") == set(get_args(Severity))
