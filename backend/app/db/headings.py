"""Where a document's nodes stand in its text (plan M1 6.5): each node at the first of its anchors'
blocks in the reading order - its heading's, as X1 anchors it (app/pipeline/x1_outline.py) - with
the depth set at it, where one is (by its notation: full, typed, skip). A node anchored nowhere has
no place in the text and is left out."""

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

_HEADINGS = """
SELECT * FROM (
    SELECT DISTINCT ON (n.id) n.id, n.parent_id, n.function_iri, n.node_type_iri, n.original_title,
        b.block_id, d.seq, depth.notation AS depth
    FROM node n
    JOIN anchor a ON a.node_id = n.id
    JOIN anchor_block b ON b.anchor_id = a.id
    JOIN document_block d ON d.conversion_id = b.conversion_id AND d.block_id = b.block_id
    LEFT JOIN vocab_concept depth ON depth.iri = n.extraction_depth_iri
    WHERE n.document_id = %s
    ORDER BY n.id, d.seq
) AS placed
ORDER BY seq, id
"""


@dataclass(frozen=True)
class NodeHeading:
    id: UUID
    parent_id: UUID | None
    function_iri: str
    node_type_iri: str | None
    title: str
    block_id: str
    depth: str | None  # the depth set at the node, where it differs from its type's


async def node_headings(connection: psycopg.AsyncConnection, document_id: UUID) -> list[NodeHeading]:
    """The document's nodes at their headings, in the reading order."""
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(_HEADINGS, (document_id,))
        rows = await cursor.fetchall()
    return [
        NodeHeading(
            id=row["id"],
            parent_id=row["parent_id"],
            function_iri=row["function_iri"],
            node_type_iri=row["node_type_iri"],
            title=row["original_title"] or "",
            block_id=row["block_id"],
            depth=row["depth"],
        )
        for row in rows
    ]
