"""Anchors (cur:SourceAnchor) as the first layer writes them (0015): of one node, statement, frame part
or specification of a document - or, naming none, of the document itself - with their blocks of the
document's conversion. Each row of the layer is an entity first (0013). X5 checks the anchors that
hold a wording against their blocks (plan M1 8.1) and writes how it stands there back.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.core.ids import new_id
from app.domain.l1 import AnchorDraft

CV = "https://w3id.org/wlo/curriculum/vocab#"
_ANCHOR = """
INSERT INTO anchor (id, document_id, conversion_id, node_id, statement_id, frame_part_id, specification_id,
    page_start, page_end, printed_page, quote, match_kind_scheme, match_kind_iri, match_score, char_start,
    char_end, table_cell)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
# A statement's anchor checks its wording, a node's its heading's title; the blocks in reading order
_UNCHECKED = """
SELECT a.id, coalesce(a.statement_id, a.node_id), coalesce(s.verbatim, n.original_title),
    array_agg(b.text ORDER BY b.seq)
FROM anchor a
LEFT JOIN statement s ON s.id = a.statement_id
LEFT JOIN node n ON n.id = a.node_id
JOIN anchor_block ab ON ab.anchor_id = a.id
JOIN document_block b ON b.conversion_id = ab.conversion_id AND b.block_id = ab.block_id
WHERE a.document_id = %s AND a.match_kind_iri IS NULL AND coalesce(s.verbatim, n.original_title) IS NOT NULL
    AND (n.rule_id IS NULL OR NOT n.rule_id = ANY(%s))
GROUP BY a.id, s.verbatim, n.original_title
ORDER BY a.id
"""
# The model named blocks the wording is not in; an anchor without blocks is an editor's that found none
_NOT_FOUND = """
SELECT a.id, coalesce(a.statement_id, a.node_id) FROM anchor a
WHERE a.document_id = %s AND a.match_kind_iri = 'https://w3id.org/wlo/curriculum/vocab#match_notFound'
    AND coalesce(a.statement_id, a.node_id) IS NOT NULL
    AND EXISTS (SELECT FROM anchor_block ab WHERE ab.anchor_id = a.id)
ORDER BY a.id
"""
# How the document's anchors of statements and nodes stand, by the notation of their match kind
_KINDS = """
SELECT replace(match_kind_iri, %s, ''), count(*) FROM anchor
WHERE document_id = %s AND coalesce(statement_id, node_id) IS NOT NULL AND match_kind_iri IS NOT NULL
GROUP BY 1 ORDER BY 1
"""
_MATCH = """
UPDATE anchor SET match_kind_scheme = %s, match_kind_iri = %s, match_score = %s, quote = %s, char_start = %s,
    char_end = %s
WHERE id = %s AND match_kind_iri IS NULL
"""


@dataclass(frozen=True)
class UncheckedAnchor:
    id: UUID
    owner: UUID  # its statement or node
    wording: str  # the statement's, or the title of the node's heading
    texts: tuple[str, ...]  # its blocks', in reading order


@dataclass(frozen=True)
class CheckedAnchor:
    id: UUID
    match_kind: str  # a concept of cv:MatchKinds
    score: float | None
    quote: str | None  # the document's text at the place
    char_start: int | None  # in the text of its blocks, one line end between two
    char_end: int | None


async def new_entity(connection: psycopg.AsyncConnection, kind: str) -> UUID:
    """A new entity of this kind, whose row the caller writes next."""
    made = new_id()
    await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, %s)", (made, kind))
    return made


async def write_anchor(
    connection: psycopg.AsyncConnection,
    document_id: UUID,
    conversion_id: UUID,
    draft: AnchorDraft,
    *,
    node_id: UUID | None = None,
    statement_id: UUID | None = None,
    frame_part_id: UUID | None = None,
    specification_id: UUID | None = None,
) -> UUID:
    """The anchor ``draft`` of the one row it names, or of the document where it names none."""
    anchor_id = await new_entity(connection, "anchor")
    match_kind = (None, None) if draft.match_kind is None else (CV + "MatchKinds", draft.match_kind)
    await connection.execute(
        _ANCHOR,
        (
            anchor_id,
            document_id,
            conversion_id,
            node_id,
            statement_id,
            frame_part_id,
            specification_id,
            draft.page_start,
            draft.page_end,
            draft.printed_page,
            draft.quote,
            *match_kind,
            draft.match_score,
            draft.char_start,
            draft.char_end,
            draft.table_cell,
        ),
    )
    async with connection.cursor() as cursor:
        await cursor.executemany(
            "INSERT INTO anchor_block (anchor_id, conversion_id, block_id) VALUES (%s, %s, %s)",
            [(anchor_id, conversion_id, block) for block in draft.block_ids],
        )
    return anchor_id


async def unchecked_anchors(
    connection: psycopg.AsyncConnection, document_id: UUID, *, rule_titles: Collection[str] = ()
) -> list[UncheckedAnchor]:
    """The document's anchors of a statement or a node's heading that have no match kind yet - but for
    the nodes of ``rule_titles``, the rules that title a node from no wording of its blocks."""
    cursor = await connection.execute(_UNCHECKED, (document_id, list(rule_titles)))
    return [
        UncheckedAnchor(found, owner, wording, tuple(texts))
        for found, owner, wording, texts in await cursor.fetchall()
    ]


async def match_kinds(connection: psycopg.AsyncConnection, document_id: UUID) -> dict[str, int]:
    """How many of the document's anchors of statements and nodes stand each way ("exact" ...)."""
    cursor = await connection.execute(_KINDS, (CV + "match_", document_id))
    return {kind: count for kind, count in await cursor.fetchall()}


async def set_matches(connection: psycopg.AsyncConnection, checked: Sequence[CheckedAnchor]) -> int:
    """Each anchor's match, where it has none yet; how many were written."""
    rows = [
        (CV + "MatchKinds", anchor.match_kind, anchor.score, anchor.quote, anchor.char_start, anchor.char_end,
         anchor.id)
        for anchor in checked
    ]  # fmt: skip
    async with connection.cursor() as cursor:
        await cursor.executemany(_MATCH, rows)  # in one pipeline, not a round trip each
        return max(cursor.rowcount, 0)


async def not_found_anchors(
    connection: psycopg.AsyncConnection, document_id: UUID
) -> list[tuple[UUID, UUID]]:
    """The anchors of statements and nodes whose wording their blocks do not hold, with whose they are."""
    cursor = await connection.execute(_NOT_FOUND, (document_id,))
    return [(found, owner) for found, owner in await cursor.fetchall()]
