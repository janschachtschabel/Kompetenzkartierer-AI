"""X1's outline against the vocabularies as loaded (plan M1 6.4): the questions list the sector's
node types with their core functions, in batches; the decisions make a tree the store takes - each
type under its function, the specifications X1 wrote applied, every node anchored."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.conversion.base import Block
from app.db.migrate import migrate
from app.db.nodes import write_subtree
from app.db.profile import write_profile
from app.db.source_queries import Reader
from app.db.tree import read_tree
from app.domain.l1 import ProfileDraft, SpecificationDraft
from app.pipeline.skeleton import build_skeleton
from app.pipeline.x1_outline import OUTLINE_BATCH, build_tree, decide
from app.pipeline.x1_question import outline_questions
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


def block(block_id: str, words: str, size: float = 10) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id,
        page=page,
        kind="text",
        text=words,
        bbox=(0, 0, 1, 1),
        font_size=size,
        bold=False,
        italic=False,
    )


BODY = "Die Schülerinnen und Schüler beschreiben, wie Licht sich ausbreitet, und erklären Schatten."
BLOCKS = [
    block("p1-b1", "Kernlehrplan Physik", size=24),
    block("p2-b1", "Kompetenzen", size=16),
    block("p2-b2", BODY),
    block("p2-b3", "Optik", size=13),
    block("p2-b4", BODY),
    block("p3-b1", "Leistungsbewertung", size=16),
    block("p3-b2", BODY),
]


def answer(
    key: str,
    node_type: str | None,
    function: str,
    applies_to: list[str] | None = None,
    share: str | None = None,
) -> dict[str, Any]:
    return {
        "headingId": key,
        "nodeType": node_type,
        "nodeFunction": function,
        "appliesTo": applies_to or [],
        "scopeShare": share,
    }


async def test_the_outline_s_decisions_make_a_tree_the_store_takes(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await document_of(connection, BLOCKS)
    skeleton = build_skeleton(BLOCKS, [], ())
    questions = await outline_questions(connection, document, skeleton, BLOCKS, [("S1", "Physik")])
    types = {iri: key for key, iri in questions.context.types.items()}
    answers = [
        answer("H1", types[SCHOOL + "Kompetenzbereich"], "area", ["S1"], "common"),
        answer("H2", types[SCHOOL + "Inhaltsbereich"], "area"),
        answer("H3", None, "frame"),
    ]

    decisions, findings = decide(skeleton, questions.asked, answers, questions.context)
    draft = ProfileDraft(
        None, None, None, None, None, None, None, None, None, (),
        (SpecificationDraft("S1", "curriculum", "Physik", None, {}, ()),), (), (),
    )  # fmt: skip
    async with connection.transaction():
        keys, _ = await write_profile(connection, document.id, draft)
        for root in build_tree(skeleton, decisions, keys):
            await write_subtree(connection, document.id, root)

    assert findings == []
    assert questions.asked == ["H1", "H2", "H3"] and len(questions.prompts) == 1
    assert f"{types[SCHOOL + 'Inhaltsbereich']}: Inhaltsbereich (Kernfunktion area)" in questions.prompts[0]
    tree = await read_tree(connection, Reader(document.owner_id, sees_all=False), document.id)
    assert tree is not None
    assert [(node.original_title, node.function_iri, node.node_type_iri) for node in tree] == [
        ("Kompetenzen", CV + "fn_area", SCHOOL + "Kompetenzbereich"),
        ("Leistungsbewertung", CV + "fn_frame", None),
    ]
    assert [(node.original_title, node.code) for node in tree[0].children] == [("Optik", "1")]
    cursor = await connection.execute(
        "SELECT n.original_title, n.applies_to = ARRAY[%s]::uuid[], n.scope_share_iri, count(b.block_id)"
        " FROM node n JOIN anchor a ON a.node_id = n.id JOIN anchor_block b ON b.anchor_id = a.id"
        " WHERE n.document_id = %s GROUP BY n.id ORDER BY n.original_title",
        (keys["S1"], document.id),
    )
    assert await cursor.fetchall() == [
        ("Kompetenzen", True, CV + "share_common", 1),
        ("Leistungsbewertung", False, None, 1),
        ("Optik", False, None, 1),
    ]


async def test_many_headings_are_asked_in_batches(connection: psycopg.AsyncConnection) -> None:
    blocks = [block("p1-b1", "Kernlehrplan Physik", size=24)]
    for number in range(1, OUTLINE_BATCH + 2):
        blocks += [
            block(f"p{number + 1}-b1", f"Abschnitt {number}", size=16),
            block(f"p{number + 1}-b2", BODY),
        ]
    document = await document_of(connection, blocks)
    skeleton = build_skeleton(blocks, [], ())

    questions = await outline_questions(connection, document, skeleton, blocks, [])

    assert len(questions.asked) == OUTLINE_BATCH + 1
    assert len(questions.prompts) == 2
    assert (
        f"H{OUTLINE_BATCH + 1} | " in questions.prompts[1]
        and f"H{OUTLINE_BATCH + 1} | " not in questions.prompts[0]
    )


async def test_no_heading_left_untyped_asks_nothing(connection: psycopg.AsyncConnection) -> None:
    document = await document_of(connection, [block("p1-b1", "Nur Text.")])
    skeleton = build_skeleton([block("p1-b1", "Nur Text.")], [], ())

    questions = await outline_questions(connection, document, skeleton, [block("p1-b1", "Nur Text.")], [])

    assert (questions.asked, questions.prompts) == ([], [])
