"""Statements added to a node that stands (app/db/nodes.py, append_statements; plan M1 7b, F10): X4
writes a unit's statements at the unit's node, from the position its part of the node begins at,
in the unit's transaction; profile values are checked as a subtree's are, and nothing is written
of statements refused or of a node another document holds."""

from typing import Any

import psycopg
import pytest

from app.db.documents import DocumentError, ProfileValueError
from app.db.nodes import append_statements, lock_tree, write_subtree
from app.db.tree import read_tree
from tests.db.test_nodes import CV, SCHOOL, anchor, connection, document, node, owner, statement, url

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_nodes


@pytest.fixture
async def unit_node(connection: psycopg.AsyncConnection, document: Any) -> Any:
    return await write_subtree(connection, document.id, node("fn_unit", code="1", anchors=(anchor("p1-b1"),)))


async def statements_of(connection: psycopg.AsyncConnection, document: Any) -> list[tuple[int, str]]:
    tree = await read_tree(connection, owner(document), document.id)
    assert tree is not None
    return [(item.position, item.verbatim) for item in tree[0].statements]


async def test_statements_are_added_at_the_node_from_the_position_given(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any
) -> None:
    ids = await append_statements(
        connection,
        document.id,
        unit_node,
        [
            statement("Die Lernenden rechnen.", subkind=SCHOOL + "Kompetenzerwartung"),
            statement("Sie prüfen."),
        ],
        first_position=10_001,
    )

    assert await statements_of(connection, document) == [
        (10_001, "Die Lernenden rechnen."),
        (10_002, "Sie prüfen."),
    ]
    cursor = await connection.execute("SELECT id FROM statement ORDER BY position")
    assert [row[0] for row in await cursor.fetchall()] == ids


async def test_the_parts_of_a_node_keep_the_document_s_order_whichever_is_written_first(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any
) -> None:
    await append_statements(
        connection, document.id, unit_node, [statement("Zweiter Teil.")], first_position=10_001
    )
    await append_statements(connection, document.id, unit_node, [statement("Erster Teil.")], first_position=1)

    assert await statements_of(connection, document) == [(1, "Erster Teil."), (10_001, "Zweiter Teil.")]


async def test_a_run_s_statements_name_their_run(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any, url: str
) -> None:
    from tests.db.l1 import add_run

    with psycopg.connect(url, autocommit=True) as sync:
        run = add_run(sync, document.id, "stage_X4")

    await append_statements(
        connection, document.id, unit_node, [statement("Mit Lauf.")], first_position=1, run_id=run
    )

    cursor = await connection.execute("SELECT run_id FROM statement")
    assert await cursor.fetchall() == [(run,)]


@pytest.mark.parametrize(
    "refused",
    [
        statement(
            "Fremde Unterart.", subkind="https://w3id.org/wlo/curriculum/profile/vocational#Kernkompetenz"
        ),
        statement(
            "Unterart zur falschen Art.", kind=CV + "kind_content", subkind=SCHOOL + "Kompetenzerwartung"
        ),
    ],
    ids=["other-profile", "other-kind"],
)
async def test_a_subkind_the_profile_does_not_hold_for_its_kind_writes_nothing(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any, refused: Any
) -> None:
    with pytest.raises(ProfileValueError):
        await append_statements(
            connection, document.id, unit_node, [statement("Gut."), refused], first_position=1
        )

    assert await statements_of(connection, document) == []


async def test_a_retired_core_value_writes_nothing(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any
) -> None:
    await connection.execute(
        "UPDATE vocab_concept SET retired_in = 1 WHERE iri = %s", (CV + "addr_educator",)
    )

    with pytest.raises(ProfileValueError) as refused:
        await append_statements(
            connection,
            document.id,
            unit_node,
            [statement("Gut."), statement("An Lehrende.", addressees=(CV + "addr_educator",))],
            first_position=1,
        )

    assert (refused.value.problem, refused.value.value) == ("retired", CV + "addr_educator")
    assert await statements_of(connection, document) == []


async def test_a_node_of_another_document_takes_none(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any, url: str
) -> None:
    from tests.db.l1 import add_conversion, add_document

    with psycopg.connect(url, autocommit=True) as sync:
        other = add_document(sync, add_conversion(sync, b"\x02" * 32))

    with pytest.raises(DocumentError):
        await append_statements(connection, other, unit_node, [statement("Fremd.")], first_position=1)

    assert await statements_of(connection, document) == []


async def test_statements_are_added_in_the_caller_s_transaction(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any
) -> None:
    with pytest.raises(RuntimeError):
        async with connection.transaction():
            await append_statements(connection, document.id, unit_node, [statement("Gut.")], first_position=1)
            raise RuntimeError("the unit broke after it")

    assert await statements_of(connection, document) == []


async def test_statements_added_wait_for_another_write_to_the_document_s_tree(
    connection: psycopg.AsyncConnection, document: Any, unit_node: Any, url: str
) -> None:
    # every write to a tree shares its lock (plan M1 4.6): an editor renumbering the node's statements
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as other, other.transaction():
        await lock_tree(other, document.id)
        await connection.execute("SET lock_timeout = '200ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            await append_statements(connection, document.id, unit_node, [statement("Gut.")], first_position=1)
