"""A document's tree as the editor reads it (plan M1 9.2, app/db/tree.py): each node with the fields of
its form, its anchors and the findings on it and its statements counted by severity; each statement with
its fields, its wording parts and its anchors - pages, quote, match and blocks in the document's order;
and the nodes and statements counted by review status."""

import uuid
from typing import Any

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.db.nodes import write_subtree
from app.db.tree import read_tree, review_counts
from app.domain.l1 import REVIEW_STATUSES, AnchorDraft
from tests.db.test_nodes import (
    CV,
    SCHOOL,
    anchor,
    connection,
    document,
    node,
    owner,
    statement,
    url,
)

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_nodes

CONFIRMED, REJECTED = CV + "rev_confirmed", CV + "rev_rejected"


async def blocks_out_of_their_names_order(connection: psycopg.AsyncConnection, document: Any) -> None:
    # p1-b2 stands before p1-b10 in the document, after it by name
    for block, seq in (("p1-b2", 3), ("p1-b10", 4)):
        await connection.execute(
            "INSERT INTO document_block (conversion_id, block_id, page, last_page, seq, kind, text,"
            " x0, top, x1, bottom, bold, italic)"
            " VALUES (%s, %s, 1, 1, %s, 'text', 'Text', 0, 0, 1, 1, false, false)",
            (document.conversion_id, block, seq),
        )


async def finding(connection: psycopg.AsyncConnection, document: Any, severity: str, focus: Any) -> None:
    await connection.execute(
        "INSERT INTO validation_finding (id, document_id, rule, severity, focus_id, message)"
        " VALUES (%s, %s, 'x5.test', %s, %s, 'found')",
        (uuid.uuid4(), document.id, severity, focus),
    )


async def anchor_of(connection: psycopg.AsyncConnection, column: str, row: Any) -> Any:
    cursor = await connection.execute(
        f"SELECT id FROM anchor WHERE {column} = %s",  # noqa: S608 - the tests' own column names
        (row,),
    )
    found = await cursor.fetchone()
    assert found is not None
    return found[0]


async def test_a_tree_holds_the_fields_of_its_nodes_and_statements(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await write_subtree(
        connection,
        document.id,
        node(
            node_type=SCHOOL + "Inhaltsbereich",
            original_title="Optik",
            obligation=CV + "obl_binding",
            statements=(
                statement(
                    "messen Lichtstärken.",
                    lead_in="Die Lernenden",
                    subkind=SCHOOL + "Kompetenzerwartung",
                    obligation=CV + "obl_elective",
                    details={"codeText": "K1", "levelText": "Niveau B"},
                ),
            ),
        ),
    )
    # details hold the wording parts alone; anything else in them is no field of the form
    await connection.execute("UPDATE statement SET details = details || %s", (Jsonb({"inherited": "x"}),))

    tree = await read_tree(connection, owner(document), document.id)

    assert tree is not None
    [area] = tree
    assert (area.original_title, area.obligation_iri) == ("Optik", CV + "obl_binding")
    [said] = area.statements
    assert (said.lead_in, said.subkind_iri, said.obligation_iri) == (
        "Die Lernenden",
        SCHOOL + "Kompetenzerwartung",
        CV + "obl_elective",
    )
    assert said.wording == {"codeText": "K1", "levelText": "Niveau B"}


async def test_a_tree_holds_the_anchors_of_its_nodes_and_statements_with_their_blocks_in_order(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await blocks_out_of_their_names_order(connection, document)
    found = AnchorDraft(
        block_ids=("p1-b10", "p1-b2"),
        page_start=1,
        page_end=2,
        printed_page="7",
        quote="Die Lernenden messen.",
        match_kind=CV + "match_fuzzy",
        match_score=0.92,
    )
    missed = AnchorDraft(block_ids=(), page_start=2, match_kind=CV + "match_notFound")
    await write_subtree(
        connection,
        document.id,
        node(
            original_title="Optik",
            anchors=(anchor("p1-b1"),),
            statements=(statement("Die Lernenden messen.", anchors=(found, missed)),),
        ),
    )

    tree = await read_tree(connection, owner(document), document.id)

    assert tree is not None
    [area] = tree
    assert [(kept.page_start, kept.blocks) for kept in area.anchors] == [(1, ("p1-b1",))]
    [said] = area.statements
    first, second = said.anchors
    assert (
        first.page_start, first.page_end, first.printed_page, first.quote, first.match_kind_iri,
        first.match_score, first.blocks,
    ) == (1, 2, "7", "Die Lernenden messen.", CV + "match_fuzzy", 0.92, ("p1-b2", "p1-b10"))  # fmt: skip
    assert isinstance(first.match_score, float)
    assert (second.page_start, second.match_kind_iri, second.blocks) == (2, CV + "match_notFound", ())


async def test_a_node_counts_the_findings_on_it_and_its_statements_by_severity(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    root = await write_subtree(
        connection,
        document.id,
        node(
            original_title="Optik",
            anchors=(anchor("p1-b1"),),
            statements=(statement("Die Lernenden messen."),),
            children=(node("fn_unit", code="1", statements=(statement("Sie prüfen."),)),),
        ),
    )
    tree = await read_tree(connection, owner(document), document.id)
    assert tree is not None
    [area] = tree
    [measured] = area.statements
    [unit] = area.children
    [checked] = unit.statements
    await finding(connection, document, "violation", root)
    await finding(connection, document, "warning", measured.id)
    await finding(connection, document, "violation", await anchor_of(connection, "statement_id", measured.id))
    await finding(connection, document, "info", await anchor_of(connection, "node_id", root))
    await finding(connection, document, "warning", checked.id)  # the child's, not its parent's
    await finding(connection, document, "violation", document.id)  # the document's, no node's

    tree = await read_tree(connection, owner(document), document.id)

    assert tree is not None
    [area] = tree
    assert area.findings == {"violation": 2, "warning": 1, "info": 1}
    assert area.children[0].findings == {"violation": 0, "warning": 1, "info": 0}


async def test_a_tree_counts_its_nodes_and_statements_by_review_status(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await write_subtree(
        connection,
        document.id,
        node(
            review_status=CONFIRMED,
            statements=(statement("Sie messen.", review_status=REJECTED), statement("Sie prüfen.")),
            children=(node("fn_unit", statements=(statement("Sie lesen."),)),),
        ),
    )
    tree = await read_tree(connection, owner(document), document.id)
    assert tree is not None

    nodes, statements = review_counts(tree)

    proposed = CV + "rev_proposed"
    assert nodes == {proposed: 1, CONFIRMED: 1, REJECTED: 0}
    assert statements == {proposed: 2, CONFIRMED: 0, REJECTED: 1}
    assert review_counts(()) == ({status: 0 for status in REVIEW_STATUSES},) * 2
