"""A frozen document stays as it was written (migration freeze; plan M1 9.6, Paket 9b H1): the database
refuses every change to its nodes, statements and their addressees, anchors and their blocks, frame
parts, specifications and their variants and its profile, and to the document's own row but its rights
status; a document not frozen changes as before. One draft at most is open under an IRI, and what a
statement's origin and run said of a hand-written one before is kept as its own mark."""

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import MIGRATIONS, migrate
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

FROZEN = "UPDATE document SET iri = %s, frozen_at = now() WHERE id = %s"
IRI = "https://example.org/doc/de/amt/lehrplan/2024"


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        seed_vocabulary(opened)
        yield opened


def filled(connection: psycopg.Connection) -> dict[str, Any]:
    """A document with one row of every kind it holds: a node with a statement, anchors with a block, a
    frame part, a specification with a variant, its profile."""
    made: dict[str, Any] = add_conversion(connection)
    document = made["document"] = add_document(connection, made)
    made["node"] = add_node(connection, document)
    made["statement"] = add_statement(connection, document, made["node"])
    made["anchor"] = add_entity(connection, "anchor")
    connection.execute(
        "INSERT INTO anchor (id, document_id, conversion_id, node_id, page_start) VALUES (%s, %s, %s, %s, 1)",
        (made["anchor"], document, made["conversion"], made["node"]),
    )
    connection.execute(
        "INSERT INTO anchor_block (anchor_id, conversion_id, block_id) VALUES (%s, %s, 'p1-b1')",
        (made["anchor"], made["conversion"]),
    )
    made["frame_part"] = add_entity(connection, "frame_part")
    connection.execute(
        "INSERT INTO frame_part (id, document_id, part_kind, content, origin_scheme, origin_iri,"
        " review_status_scheme, review_status_iri, position)"
        " VALUES (%s, %s, 'operators', '{}', %s, %s, %s, %s, 1)",
        (made["frame_part"], document, CV + "Origins", CV + "orig_source", CV + "ReviewStatuses",
         CV + "rev_proposed"),
    )  # fmt: skip
    made["specification"] = add_specification(connection, document)
    made["variant"] = add_variant(connection, made["specification"])
    connection.execute("INSERT INTO document_profile (document_id) VALUES (%s)", (document,))
    return made


# Each a change to one table of the document's rows: a statement's own, and what it is passed
CHANGES = {
    "node added": (
        "INSERT INTO node (id, document_id, position, function_scheme, function_iri, origin_scheme,"
        " origin_iri, review_status_scheme, review_status_iri) SELECT %(entity_node)s, %(document)s, 2,"
        " function_scheme, function_iri, origin_scheme, origin_iri, review_status_scheme, review_status_iri"
        " FROM node WHERE id = %(node)s"
    ),
    "node changed": "UPDATE node SET original_title = 'Neu' WHERE id = %(node)s",
    "node taken away": "DELETE FROM node WHERE id = %(node)s",
    "statement changed": "UPDATE statement SET lead_in = 'Die' WHERE id = %(statement)s",
    "statement taken away": "DELETE FROM statement WHERE id = %(statement)s",
    "addressee added": (
        "INSERT INTO statement_addressee (statement_id, addressee_scheme, addressee_iri)"
        " VALUES (%(statement)s, %(addressees)s, %(teacher)s)"
    ),
    "addressee taken away": "DELETE FROM statement_addressee WHERE statement_id = %(statement)s",
    "anchor changed": "UPDATE anchor SET printed_page = '7' WHERE id = %(anchor)s",
    "anchor taken away": "DELETE FROM anchor WHERE id = %(anchor)s",
    "block taken away": "DELETE FROM anchor_block WHERE anchor_id = %(anchor)s",
    "block added": (
        "INSERT INTO anchor_block (anchor_id, conversion_id, block_id)"
        " VALUES (%(anchor)s, %(conversion)s, 'p2-b1')"
    ),
    "frame part changed": "UPDATE frame_part SET content = '{\"a\": 1}' WHERE id = %(frame_part)s",
    "specification changed": "UPDATE specification SET title = 'Neu' WHERE id = %(specification)s",
    "variant changed": "UPDATE variant SET label = 'Neu' WHERE id = %(variant)s",
    "variant taken away": "DELETE FROM variant WHERE id = %(variant)s",
    "profile changed": "UPDATE document_profile SET new_terms = '[1]' WHERE document_id = %(document)s",
    "document renamed": "UPDATE document SET title = 'Neu' WHERE id = %(document)s",
    "document unfrozen": "UPDATE document SET frozen_at = NULL WHERE id = %(document)s",
    "document taken away": "DELETE FROM document WHERE id = %(document)s",
}


def change(connection: psycopg.Connection, made: dict[str, Any], name: str) -> None:
    passed = {"entity_node": add_entity(connection, "node"), "addressees": CV + "Addressees",
              "teacher": CV + "addr_teacher"}  # fmt: skip
    connection.execute(CHANGES[name], made | passed)


@pytest.mark.parametrize("name", list(CHANGES), ids=list(CHANGES))
def test_no_row_of_a_frozen_document_changes(connection: psycopg.Connection, name: str) -> None:
    made = filled(connection)
    connection.execute(FROZEN, (IRI, made["document"]))

    with pytest.raises(errors.ObjectNotInPrerequisiteState):
        change(connection, made, name)


@pytest.mark.parametrize("name", [name for name in CHANGES if name != "document unfrozen"])
def test_the_rows_of_a_document_not_frozen_change_as_before(
    connection: psycopg.Connection, name: str
) -> None:
    # rolled back: the deferred guards (an addressee and an anchor at least) are not what this is about
    made = filled(connection)

    with connection.transaction(force_rollback=True):
        change(connection, made, name)


def test_a_frozen_document_s_rights_status_changes_still(connection: psycopg.Connection) -> None:
    made = filled(connection)
    connection.execute(FROZEN, (IRI, made["document"]))

    connection.execute("UPDATE document SET rights_status = 'amtlich', updated_at = now() WHERE id = %s",
                       (made["document"],))  # fmt: skip

    found = connection.execute(
        "SELECT rights_status FROM document WHERE id = %s", (made["document"],)
    ).fetchone()
    assert found == ("amtlich",)


def test_another_document_s_rows_change_beside_a_frozen_one(connection: psycopg.Connection) -> None:
    made = filled(connection)
    connection.execute(FROZEN, (IRI, made["document"]))
    other = add_document(connection, made)

    node = add_node(connection, other)
    add_statement(connection, other, node)
    connection.execute("UPDATE node SET original_title = 'Neu' WHERE id = %s", (node,))


def test_one_draft_at_most_is_open_under_an_iri(connection: psycopg.Connection) -> None:
    made = add_conversion(connection)
    frozen = add_document(connection, made, iri=IRI)
    connection.execute("UPDATE document SET frozen_at = now() WHERE id = %s", (frozen,))
    add_document(connection, made, iri=IRI, revision=2, copy_of=frozen)

    with pytest.raises(errors.UniqueViolation):
        add_document(connection, made, iri=IRI, revision=3, copy_of=frozen)


def test_a_copy_carries_the_iri_of_the_revision_it_copies(connection: psycopg.Connection) -> None:
    made = add_conversion(connection)
    frozen = add_document(connection, made, iri=IRI)

    with pytest.raises(errors.CheckViolation):
        add_document(connection, made, copy_of=frozen)


def test_a_node_or_statement_iri_names_one_row_of_its_document(connection: psycopg.Connection) -> None:
    made = add_conversion(connection)
    document = add_document(connection, made)
    first = add_node(connection, document, iri=IRI + "/1")
    add_statement(connection, document, first, iri=IRI + "/1/s-1")

    with pytest.raises(errors.UniqueViolation):
        add_node(connection, document, position=2, iri=IRI + "/1")
    with pytest.raises(errors.UniqueViolation):
        add_statement(connection, document, first, position=2, iri=IRI + "/1/s-1")
    with pytest.raises(errors.CheckViolation):
        add_node(connection, document, position=3, iri="urn:uuid:" + str(uuid.uuid4()))


def test_a_statement_written_by_hand_before_keeps_that_mark(database_url: str, tmp_path: Path) -> None:
    # by origin and run, as drop_or_reject_statement told them apart before (app/db/statement_editing.py)
    before = tmp_path / "migrations"
    before.mkdir()
    for migration in MIGRATIONS.iterdir():
        if migration.name.endswith(".sql") and migration.name < "0022":
            shutil.copyfile(str(migration), before / migration.name)
    migrate(database_url, before)
    with psycopg.connect(database_url, autocommit=True) as connection:
        seed_vocabulary(connection)
        made = add_conversion(connection)
        document = add_document(connection, made)
        node = add_node(connection, document)
        run = add_run(connection, document)
        by_hand = add_statement(connection, document, node, origin_iri=CV + "orig_human")
        edited = add_statement(
            connection, document, node, position=2, origin_iri=CV + "orig_human", run_id=run
        )
        modelled = add_statement(connection, document, node, position=3, origin_iri=CV + "orig_model")

        migrate(database_url)

        rows = connection.execute("SELECT id, by_hand FROM statement").fetchall()
    assert dict(rows) == {by_hand: True, edited: False, modelled: False}
