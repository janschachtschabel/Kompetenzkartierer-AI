"""Frame parts as X3 writes and X4 reads them (plan M1 7b, 0015): a competency or level model, an
operator, a legend entry or a rule of the document's frame - each its schema object as X3 gave it,
without the blocks it names, which its anchor holds. Written in the caller's transaction, the one
that ends X3's run; read back in the order they were written (their ids grow with time).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.db.anchors import CV, new_entity, write_anchor
from app.domain.l1 import AnchorDraft, FramePartKind

_PART = """
INSERT INTO frame_part (id, document_id, part_kind, content, origin_scheme, origin_iri, review_status_scheme,
    review_status_iri, rule_id, run_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""
_PARTS = "SELECT id, part_kind, content, run_id FROM frame_part WHERE document_id = %s ORDER BY id"


@dataclass(frozen=True)
class FramePartDraft:
    kind: FramePartKind
    content: Mapping[str, Any]  # the schema object, its block ids taken out into ``anchor``
    anchor: AnchorDraft
    origin: str  # a concept of cv:Origins
    review_status: str  # a concept of cv:ReviewStatuses
    rule_id: str | None = None  # the rule a part of origin rule follows


@dataclass(frozen=True)
class FramePart:
    id: UUID
    kind: FramePartKind
    content: dict[str, Any]
    run_id: UUID | None


async def write_frame_parts(
    connection: psycopg.AsyncConnection,
    document_id: UUID,
    conversion_id: UUID,
    drafts: Sequence[FramePartDraft],
    *,
    run_id: UUID,
) -> list[UUID]:
    """The parts, each with its anchor in the document's conversion, in the caller's transaction."""
    made = []
    for draft in drafts:
        part_id = await new_entity(connection, "frame_part")
        await connection.execute(
            _PART,
            (
                part_id,
                document_id,
                draft.kind,
                Jsonb(dict(draft.content)),
                CV + "Origins",
                draft.origin,
                CV + "ReviewStatuses",
                draft.review_status,
                draft.rule_id,
                run_id,
            ),
        )
        await write_anchor(connection, document_id, conversion_id, draft.anchor, frame_part_id=part_id)
        made.append(part_id)
    return made


async def frame_parts_of(connection: psycopg.AsyncConnection, document_id: UUID) -> list[FramePart]:
    """The document's frame parts, in the order they were written."""
    cursor = await connection.execute(_PARTS, (document_id,))
    return [FramePart(*row) for row in await cursor.fetchall()]
