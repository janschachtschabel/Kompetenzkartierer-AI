"""The editors' review of a document's nodes and statements (plan M1 9.5; Paket 9 G8): one review status for
many rows at once, all or nothing - each row on the revision it was read at, else none is set
(StaleItems names those that stand otherwise, or no more). A row set counts its revision one up and keeps
its origin: a review is no edit. It holds the tree's lock and refuses beside an open job, before X4 is
done and once the document is frozen, as every change does (app/db/editing.py, ``guard``).

A review changes not what the document says - X5 checks no review status -, but a statement rejected, or
taken back from rejected, enters or leaves the curriculum (the Kern export and X5 leave rejected ones
out): that edits the document (``document.edited_at``). A node rejected stays in both.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import psycopg

from app.db.editing import CV, guard, mark_edited

ReviewKind = Literal["node", "statement"]
REJECTED = CV + "rev_rejected"
_KINDS: tuple[ReviewKind, ...] = ("node", "statement")
_CURRENT = (
    "SELECT id, revision, review_status_iri FROM {table} WHERE document_id = %s AND id = ANY(%s) FOR UPDATE"
)
_SET = """
UPDATE {table} SET review_status_iri = %s, revision = revision + 1, updated_at = now()
WHERE id = ANY(%s) RETURNING id, revision
"""


@dataclass(frozen=True)
class ReviewItem:
    kind: ReviewKind
    id: UUID
    revision: int  # the row's, as it was read


@dataclass(frozen=True)
class Stale:
    kind: ReviewKind
    id: UUID
    current: int | None  # the row's revision now; none where the document holds no such row


class StaleItems(Exception):
    """Rows of a review that stand at another revision than it was made on, or no more: none was set."""

    def __init__(self, stale: list[Stale]) -> None:
        super().__init__(f"{len(stale)} rows stand otherwise")
        self.stale = stale


async def set_review(
    connection: psycopg.AsyncConnection, document_id: UUID, status: str, items: Sequence[ReviewItem]
) -> dict[UUID, int]:
    """Set the review status ``status`` (an IRI of cv:ReviewStatuses) of the document's rows ``items``; the
    revision of each after - one already at the status stays as it is. A row named twice is set once, on
    the revision named first. StaleItems or a refusal of ``guard``, and then none is set."""
    first: dict[tuple[str, UUID], ReviewItem] = {}
    for item in items:
        first.setdefault((item.kind, item.id), item)
    named = list(first.values())
    async with connection.transaction():
        await guard(connection, document_id)
        found: dict[tuple[str, UUID], tuple[int, str]] = {}
        for kind in _KINDS:
            ids = [item.id for item in named if item.kind == kind]
            if ids:
                cursor = await connection.execute(_CURRENT.format(table=kind), (document_id, ids))
                found |= {(kind, row): (revision, now) for row, revision, now in await cursor.fetchall()}
        stale = []
        for item in named:
            current = found.get((item.kind, item.id))
            if current is None or current[0] != item.revision:
                stale.append(Stale(item.kind, item.id, None if current is None else current[0]))
        if stale:
            raise StaleItems(stale)
        revisions = {item.id: found[(item.kind, item.id)][0] for item in named}
        edited = False
        for kind in _KINDS:
            changing = [
                item.id for item in named if item.kind == kind and found[(kind, item.id)][1] != status
            ]
            if not changing:
                continue
            cursor = await connection.execute(_SET.format(table=kind), (status, changing))
            revisions |= {row: revision for row, revision in await cursor.fetchall()}
            was = {found[(kind, row)][1] for row in changing}
            edited = edited or (kind == "statement" and REJECTED in {status, *was})
        if edited:
            await mark_edited(connection, document_id)
        return revisions
