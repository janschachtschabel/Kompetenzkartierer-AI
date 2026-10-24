"""Anchors (cur:SourceAnchor) as the first layer writes them (0015): of one node, statement, frame part
or specification of a document - or, naming none, of the document itself - with their blocks of the
document's conversion. Each row of the layer is an entity first (0013)."""

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
