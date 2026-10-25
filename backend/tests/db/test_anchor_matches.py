"""The anchors X5 checks against their blocks (plan M1 8.1): those of a statement or of a node's heading
that have no match kind yet, each with the wording to check and its blocks' texts in reading order -
and the match written back, only where none is: a match kind once set, X5's or an editor's, stays."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.conversion.base import Block
from app.db.anchors import CheckedAnchor, set_matches, unchecked_anchors, write_anchor
from app.db.migrate import migrate
from app.db.nodes import write_subtree
from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
MODEL, PROPOSED = CV + "orig_model", CV + "rev_proposed"
WORDING = "Die Lernenden beschreiben Licht und Schatten."


def block(block_id: str, text: str) -> Block:
    return Block(
        id=block_id, page=1, kind="text", text=text, bbox=(0, 0, 1, 1), font_size=10, bold=False, italic=False
    )


BLOCKS = [
    block("p1-b1", "Kompetenzen"),
    block("p1-b2", "Die Lernenden beschreiben"),
    block("p1-b3", "Licht und Schatten."),
]


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


def statement(verbatim: str, anchor: AnchorDraft) -> StatementDraft:
    return StatementDraft(
        verbatim=verbatim, kind=CV + "kind_learningOutcome", addressees=(CV + "addr_learner",),
        anchors=(anchor,), origin=MODEL, review_status=PROPOSED,
    )  # fmt: skip


async def a_tree(connection: psycopg.AsyncConnection) -> Any:
    """A document whose heading and one statement are unchecked, a statement already checked, and an
    anchor of the document itself (X1's, no wording)."""
    document = await document_of(connection, BLOCKS)
    checked = AnchorDraft(
        ("p1-b2",), page_start=1, quote="Die Lernenden beschreiben", match_kind=CV + "match_exact"
    )
    root = NodeDraft(
        function=CV + "fn_area", origin=MODEL, review_status=PROPOSED, original_title="Kompetenzen",
        anchors=(AnchorDraft(("p1-b1",), page_start=1),),
        statements=(
            statement(WORDING, AnchorDraft(("p1-b3", "p1-b2"), page_start=1)),  # named out of order
            statement("Die Lernenden beschreiben", checked),
        ),
    )  # fmt: skip
    await write_subtree(connection, document.id, root)
    await write_anchor(connection, document.id, document.conversion_id, AnchorDraft(("p1-b1",), page_start=1))
    return document


async def test_the_anchors_to_check_have_a_wording_and_no_match_kind_their_texts_in_reading_order(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await a_tree(connection)
    await a_tree(connection)  # another document's are not this one's

    found = await unchecked_anchors(connection, document.id)

    cursor = await connection.execute(
        "SELECT (SELECT id FROM node WHERE document_id = %(d)s),"
        " (SELECT id FROM statement WHERE document_id = %(d)s AND verbatim = %(w)s)",
        {"d": document.id, "w": WORDING},
    )
    [(node, told)] = await cursor.fetchall()
    assert sorted((anchor.wording, anchor.texts, anchor.owner) for anchor in found) == [
        (WORDING, ("Die Lernenden beschreiben", "Licht und Schatten."), told),  # whose: the finding's focus
        ("Kompetenzen", ("Kompetenzen",), node),
    ]


async def test_a_match_is_written_where_none_is_and_a_set_one_stays(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await a_tree(connection)
    found = await unchecked_anchors(connection, document.id)
    cursor = await connection.execute(
        "SELECT id FROM anchor WHERE document_id = %s AND match_kind_iri IS NOT NULL", (document.id,)
    )
    [(already,)] = await cursor.fetchall()
    matches = [
        CheckedAnchor(anchor.id, CV + "match_fuzzy", 0.912, anchor.texts[0], 0, 11) for anchor in found
    ]

    written = await set_matches(
        connection, [*matches, CheckedAnchor(already, CV + "match_notFound", None, None, None, None)]
    )

    assert written == 2
    assert await unchecked_anchors(connection, document.id) == []
    cursor = await connection.execute(
        "SELECT match_kind_scheme, match_kind_iri, match_score::float, quote, char_start, char_end"
        " FROM anchor WHERE document_id = %s AND match_kind_iri IS NOT NULL",
        (document.id,),
    )
    assert sorted(await cursor.fetchall(), key=str) == [
        (CV + "MatchKinds", CV + "match_exact", None, "Die Lernenden beschreiben", None, None),
        (CV + "MatchKinds", CV + "match_fuzzy", 0.912, "Die Lernenden beschreiben", 0, 11),
        (CV + "MatchKinds", CV + "match_fuzzy", 0.912, "Kompetenzen", 0, 11),
    ]
