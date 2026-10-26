"""The anchors X5 checks against their blocks (plan M1 8.1): those of a statement or of a node's heading
that have no match kind yet, each with the wording to check and its blocks' texts in reading order -
and the match written back, only where none is: a match kind once set, X5's or an editor's, stays."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.conversion.base import Block
from app.db.anchors import (
    CheckedAnchor,
    match_kinds,
    not_found_anchors,
    set_matches,
    unchecked_anchors,
    write_anchor,
)
from app.db.migrate import migrate
from app.db.nodes import write_subtree
from app.db.profile import write_profile
from app.domain.l1 import AnchorDraft, NodeDraft, ProfileDraft, SpecificationDraft, StatementDraft
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
    """A document whose heading and one statement are unchecked, a statement already checked, and the
    anchors of the document itself and of a specification (X1's, no wording)."""
    document = await document_of(connection, BLOCKS)
    profile = ProfileDraft(
        title=None, document_type=None, legal_form=None, binding=None, lifecycle=None, issuer=None,
        edition=None, issued=None, valid_from=None, evidence=(),
        specifications=(SpecificationDraft("S1", "curriculum", "Physik", None, {}, ("p1-b1",)),),
        term_mappings=(), new_terms=(),
    )  # fmt: skip
    await write_profile(connection, document.id, profile)
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


async def test_the_anchors_whose_wording_was_not_found_are_those_with_blocks_the_model_named(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await a_tree(connection)
    [told, heading] = sorted(  # "Die Lernenden …" before "Kompetenzen"
        await unchecked_anchors(connection, document.id), key=lambda anchor: anchor.wording
    )
    await set_matches(
        connection,
        [
            CheckedAnchor(heading.id, CV + "match_exact", None, "Kompetenzen", 0, 11),
            CheckedAnchor(told.id, CV + "match_notFound", None, None, None, None),
        ],
    )
    # an editor's anchor that found no block (plan M1 9.4): no claim of the model
    await write_anchor(
        connection, document.id, document.conversion_id,
        AnchorDraft((), page_start=1, match_kind=CV + "match_notFound"), statement_id=told.owner,
    )  # fmt: skip

    assert await not_found_anchors(connection, document.id) == [(told.id, told.owner)]


async def test_the_anchor_of_a_node_a_rule_titled_is_not_checked(connection: psycopg.AsyncConnection) -> None:
    # X4 titles a node of its own by the document (app/pipeline/x4_unit.py): its anchor says where the unit
    # begins, not that the title stands there
    document = await document_of(connection, BLOCKS)
    titled = NodeDraft(
        function=CV + "fn_unit", origin=CV + "orig_rule", review_status=PROPOSED, original_title="Dokument",
        rule_id="x4.unit_without_node", anchors=(AnchorDraft(("p1-b2",), page_start=1),),
    )  # fmt: skip
    await write_subtree(connection, document.id, titled)

    assert await unchecked_anchors(connection, document.id, rule_titles=("x4.unit_without_node",)) == []
    assert [anchor.wording for anchor in await unchecked_anchors(connection, document.id)] == ["Dokument"]


async def test_a_rejected_statement_s_anchors_are_neither_checked_nor_counted(
    connection: psycopg.AsyncConnection,
) -> None:
    # a rejected statement is no part of the curriculum (Paket 9 G9): X5 checks its wording no more
    document = await a_tree(connection)
    [told, _] = sorted(await unchecked_anchors(connection, document.id), key=lambda anchor: anchor.wording)
    await connection.execute(
        "UPDATE statement SET review_status_iri = %s WHERE document_id = %s",
        (CV + "rev_rejected", document.id),
    )

    assert [anchor.wording for anchor in await unchecked_anchors(connection, document.id)] == ["Kompetenzen"]
    await set_matches(connection, [CheckedAnchor(told.id, CV + "match_notFound", None, None, None, None)])
    assert await not_found_anchors(connection, document.id) == []
    assert await match_kinds(connection, document.id) == {}  # the exact one, too, was a statement's
