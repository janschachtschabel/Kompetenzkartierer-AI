"""The tables of a document's structure and statements (migration l1_nodes, plan M1 4.3): a tree
without cycles within one document, values that fit their core values, an addressee for each
statement."""

import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import migrate
from tests.db.l1 import (
    CV,
    SCHOOL,
    add_conversion,
    add_document,
    add_entity,
    add_node,
    add_statement,
    seed_vocabulary,
)

pytestmark = pytest.mark.pg


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        seed_vocabulary(opened)
        yield opened


@pytest.fixture
def document(connection: psycopg.Connection) -> uuid.UUID:
    return add_document(connection, add_conversion(connection))


def test_a_tree_of_nodes_is_held_and_none_comes_to_lie_under_itself(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    root = add_node(connection, document)
    child = add_node(connection, document, root)
    grandchild = add_node(connection, document, child)

    with pytest.raises(errors.CheckViolation):
        connection.execute("UPDATE node SET parent_id = %s WHERE id = %s", (grandchild, root))
    with pytest.raises(errors.CheckViolation):
        connection.execute("UPDATE node SET parent_id = id WHERE id = %s", (child,))
    connection.execute("UPDATE node SET parent_id = %s, position = 2 WHERE id = %s", (root, grandchild))


def test_nodes_written_in_a_circle_at_once_are_refused(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    # each the other's parent, in one statement: the foreign key holds once both rows stand
    first, second = add_entity(connection, "node"), add_entity(connection, "node")
    columns = (
        "id, document_id, parent_id, position, function_scheme, function_iri, origin_scheme, origin_iri,"
    )
    columns += " review_status_scheme, review_status_iri"
    row = "(%s, %s, %s, 1, %s, %s, %s, %s, %s, %s)"
    values = [CV + "NodeFunctions", CV + "fn_area", CV + "Origins", CV + "orig_source"]
    values += [CV + "ReviewStatuses", CV + "rev_proposed"]

    with pytest.raises(errors.CheckViolation, match="under itself"):
        connection.execute(
            f"INSERT INTO node ({columns}) VALUES {row}, {row}",  # noqa: S608 - the test's own names
            (first, document, second, *values, second, document, first, *values),
        )


def test_a_node_is_moved_under_read_committed_alone(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    # under repeatable read two moves could each close a circle the other does not see
    root = add_node(connection, document)
    child = add_node(connection, document, position=2)

    with pytest.raises(errors.InvalidTransactionState, match="read committed"), connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("UPDATE node SET parent_id = %s WHERE id = %s", (root, child))


def test_a_node_lies_under_a_node_of_its_own_document(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    other = add_document(connection, add_conversion(connection, b"\x02" * 32))
    foreign = add_node(connection, other)

    with pytest.raises(errors.ForeignKeyViolation):
        add_node(connection, document, foreign)


def test_siblings_stand_at_places_of_their_own_at_the_top_too(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    root = add_node(connection, document)
    add_node(connection, document, root, 1)

    with pytest.raises(errors.UniqueViolation):
        add_node(connection, document, root, 1)
    with pytest.raises(errors.UniqueViolation):
        add_node(connection, document)


def test_a_node_type_lies_under_the_node_s_function(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    node = add_node(connection, document, node_type_iri=SCHOOL + "Inhaltsbereich")

    with pytest.raises(errors.CheckViolation):
        add_node(
            connection,
            document,
            position=2,
            function_iri=CV + "fn_unit",
            node_type_iri=SCHOOL + "Inhaltsbereich",
        )
    with pytest.raises(errors.CheckViolation):
        connection.execute("UPDATE node SET function_iri = %s WHERE id = %s", (CV + "fn_unit", node))


@pytest.mark.parametrize(
    "columns",
    [
        {"origin_iri": CV + "orig_rule"},  # a rule's value without the rule
        {"rule_id": "code-from-position"},  # a rule named for a value from the source
        {"code_assigned": True},  # an assigned code that is none
        {"position": 0},
        {"title_language": "Deutsch"},
    ],
    ids=["rule-without-id", "id-without-rule", "assigned-code", "position", "language"],
)
def test_a_node_s_values_keep_their_forms(
    connection: psycopg.Connection, document: uuid.UUID, columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_node(connection, document, **columns)


def test_a_value_from_a_rule_names_the_rule(connection: psycopg.Connection, document: uuid.UUID) -> None:
    node = add_node(
        connection,
        document,
        origin_iri=CV + "orig_rule",
        rule_id="code-from-position",
        code="1",
        code_assigned=True,
    )

    assert connection.execute("SELECT rule_id FROM node WHERE id = %s", (node,)).fetchone() == (
        "code-from-position",
    )


def test_a_statement_stands_at_a_node_of_its_document_with_an_addressee(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    node = add_node(connection, document)
    statement = add_statement(connection, document, node, addressees=("addr_learner", "addr_teacher"))

    addressees = connection.execute(
        "SELECT addressee_iri FROM statement_addressee WHERE statement_id = %s ORDER BY addressee_iri",
        (statement,),
    ).fetchall()
    assert addressees == [(CV + "addr_learner",), (CV + "addr_teacher",)]

    other = add_document(connection, add_conversion(connection, b"\x02" * 32))
    with pytest.raises(errors.ForeignKeyViolation):
        add_statement(connection, other, node, position=2)


def test_a_statement_without_an_addressee_is_refused_when_it_is_committed(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    node = add_node(connection, document)

    with pytest.raises(errors.CheckViolation, match="addressee"):
        add_statement(connection, document, node, addressees=())


def test_a_statement_s_last_addressee_stays(connection: psycopg.Connection, document: uuid.UUID) -> None:
    statement = add_statement(
        connection, document, add_node(connection, document), addressees=("addr_learner",)
    )

    with pytest.raises(errors.CheckViolation, match="addressee"):
        connection.execute("DELETE FROM statement_addressee WHERE statement_id = %s", (statement,))


def test_an_addressee_is_one_of_the_core_s(connection: psycopg.Connection, document: uuid.UUID) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        add_statement(connection, document, add_node(connection, document), addressees=("fn_area",))


@pytest.mark.parametrize(
    "columns",
    [
        {"subkind_iri": SCHOOL + "Kompetenzerwartung", "statement_kind_iri": CV + "kind_content"},
        {"verbatim": "   "},
        {"text_hash": "abc"},
        {"details": psycopg.types.json.Jsonb([])},
    ],
    ids=["subkind-of-another-kind", "no-wording", "hash", "details"],
)
def test_a_statement_s_values_keep_their_forms(
    connection: psycopg.Connection, document: uuid.UUID, columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_statement(connection, document, add_node(connection, document), **columns)


def test_a_subkind_lies_under_its_statement_s_kind(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    statement = add_statement(
        connection, document, add_node(connection, document), subkind_iri=SCHOOL + "Kompetenzerwartung"
    )

    with pytest.raises(errors.CheckViolation):
        connection.execute(
            "UPDATE statement SET statement_kind_iri = %s WHERE id = %s", (CV + "kind_content", statement)
        )


def test_a_node_taken_away_takes_its_children_and_statements(
    connection: psycopg.Connection, document: uuid.UUID
) -> None:
    root = add_node(connection, document)
    child = add_node(connection, document, root)
    add_statement(connection, document, child)

    connection.execute("DELETE FROM node WHERE id = %s", (root,))

    assert connection.execute(
        "SELECT (SELECT count(*) FROM node), (SELECT count(*) FROM statement)"
    ).fetchone() == (
        0,
        0,
    )
