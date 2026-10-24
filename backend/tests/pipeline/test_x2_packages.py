"""X2's work packages of a document as written (plan M1 6.5): its nodes found at their headings'
blocks, each node's depth its type's from the vocabularies, else its function's."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.conversion.base import Block
from app.db.headings import node_headings
from app.db.migrate import migrate
from app.db.nodes import write_subtree
from app.domain.l1 import AnchorDraft, NodeDraft
from app.pipeline.x2_segments import work_packages
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


def block(block_id: str, words: str = "Text.") -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id,
        page=page,
        kind="text",
        text=words,
        bbox=(0, 0, 1, 1),
        font_size=10,
        bold=False,
        italic=False,
    )


BLOCKS = [
    block("p1-b1", "Kernlehrplan Physik"),
    block("p2-b1", "Kompetenzen"),
    block("p2-b2"),
    block("p2-b3", "Optik"),
    block("p2-b4"),
    block("p3-b1", "Leistungsbewertung"),
    block("p3-b2"),
]


def node(title: str, at: str, page: int, function: str, **changes: Any) -> NodeDraft:
    values: dict[str, Any] = {
        "function": CV + function,
        "origin": CV + "orig_model",
        "review_status": CV + "rev_proposed",
        "original_title": title,
        "anchors": (AnchorDraft(block_ids=(at,), page_start=page, quote=title),),
    } | changes
    return NodeDraft(**values)


async def test_a_document_s_packages_follow_its_nodes_at_their_headings(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await document_of(connection, BLOCKS)
    optics = node("Optik", "p2-b3", 2, "fn_area", node_type=SCHOOL + "Inhaltsbereich")
    async with connection.transaction():
        await write_subtree(
            connection, document.id, node("Kompetenzen", "p2-b1", 2, "fn_area", children=(optics,))
        )
        await write_subtree(
            connection,
            document.id,
            node("Leistungsbewertung", "p3-b1", 3, "fn_frame", node_type=SCHOOL + "Rahmenteil"),
        )

    headings = await node_headings(connection, document.id)
    packages = await work_packages(connection, document.id, BLOCKS)

    assert [(heading.title, heading.block_id) for heading in headings] == [
        ("Kompetenzen", "p2-b1"),
        ("Optik", "p2-b3"),
        ("Leistungsbewertung", "p3-b1"),
    ]
    assert headings[1].parent_id == headings[0].id
    assert [(item.key, item.first_block, item.depth, item.job, item.path) for item in packages] == [
        ("E0", "p1-b1", "typed", "frame", ()),
        ("E1", "p2-b1", "full", "statements", ("Kompetenzen",)),
        ("E2", "p2-b3", "full", "statements", ("Kompetenzen", "Optik")),
        ("E3", "p3-b1", "typed", "frame", ("Leistungsbewertung",)),  # the Rahmenteil's depth: typed
    ]
    assert packages[1].node_id == headings[0].id
