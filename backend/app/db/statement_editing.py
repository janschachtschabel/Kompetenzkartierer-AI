"""An editor's changes to a document's statements (plan M1 9.4; Paket 9 G2-G7), as app/db/editing.py makes
a node's - the tree's lock first, then no frozen document and no open job, the revision named, the
statement an editor's proposal after, the document edited.

A statement's fields go by the form's keys - its wording parts among them, kept in its details beside
whatever else they hold -, its addressees as one of them, all at once. Its anchors are given whole or
not at all: each the blocks of the document's conversion where the editor found it, its pages theirs,
for X5 to check; or, where no block holds it, the page it stands on (match kind notFound). A new wording
takes its hash, and its anchors with blocks are checked anew. A statement taken away a run wrote is
rejected and stays, so that no repair proposes it again; one an editor wrote is deleted, with the
findings on it and its anchors.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, LiteralString
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.db.anchors import write_anchor
from app.db.documents import DOCUMENT_VISIBLE
from app.db.editing import (
    CV,
    DOCUMENT_OF_NODE,
    HUMAN,
    OBLIGATION,
    PROPOSED,
    SECTOR,
    check_revision,
    drop_findings,
    edit_query,
    every_field,
    form_for,
    guard,
    leave_unchecked,
    mark_edited,
    returned_revision,
    row_of,
    target_of,
    text,
)
from app.db.nodes import append_statements
from app.db.source_queries import Reader
from app.domain.l1 import MATCH_NOT_FOUND, WORDING_FIELDS, AnchorDraft, StatementDraft
from app.domain.wording import text_hash
from app.vocab.form_values import FieldError, check_under, checked
from app.vocab.forms import STATEMENT_FIELDS

REJECTED = CV + "rev_rejected"
DOCUMENT_OF_STATEMENT = f"""
SELECT d.id, sector.notation FROM statement s JOIN document d ON d.id = s.document_id {SECTOR}
WHERE s.id = %(id)s AND {DOCUMENT_VISIBLE}
"""  # noqa: S608 - fixed parts
_STATEMENT = """
SELECT s.revision, s.verbatim, s.lead_in, s.statement_kind_iri AS statement_kind, s.subkind_iri AS subkind,
    s.obligation_iri AS obligation,
    array(
        SELECT a.addressee_iri FROM statement_addressee a WHERE a.statement_id = s.id ORDER BY 1
    ) AS addressees,
    s.details
FROM statement s WHERE s.id = %s FOR UPDATE
"""
# named where their value changes alone, as a node's (app/db/editing.py): the pair's trigger subkind_fits
_COLUMNS: dict[str, LiteralString] = {
    "verbatim": "verbatim = %(verbatim)s, text_hash = %(hash)s",
    "lead_in": "lead_in = %(lead_in)s",
    "statement_kind": "statement_kind_iri = %(statement_kind)s",
    "subkind": "subkind_iri = %(subkind)s",
    "obligation": OBLIGATION,
}
_PAGES = """
SELECT count(*), min(page), max(last_page) FROM document_block
WHERE conversion_id = (SELECT conversion_id FROM document WHERE id = %s) AND block_id = ANY(%s)
"""
_CONVERSION_PAGES = (
    "SELECT coalesce(c.pages, 0) FROM document d JOIN conversion c ON c.id = d.conversion_id WHERE d.id = %s"
)
_TAKEN = """
SELECT s.revision, s.origin_iri = %s AND s.run_id IS NULL AS by_hand, s.review_status_iri = %s AS rejected,
    array(SELECT id FROM anchor WHERE statement_id = s.id) AS anchors
FROM statement s WHERE s.id = %s FOR UPDATE
"""


@dataclass(frozen=True)
class HandAnchor:
    """Where an editor found a statement: blocks of the document's conversion - its pages follow from
    them -, or none, the wording found in no block, and the page it stands on, from 1."""

    blocks: tuple[str, ...] = ()
    page: int | None = None


async def edit_statement(
    connection: psycopg.AsyncConnection,
    reader: Reader,
    statement_id: UUID,
    revision: int,
    given: Mapping[str, object],
    *,
    anchors: Sequence[HandAnchor] | None = None,
) -> int | None:
    """Set the statement's fields ``given`` by the form's keys - and its anchors, where ``anchors`` names
    them, in place of those it has - on its revision ``revision``; its revision after, None where
    ``reader`` sees no such statement. StaleRevision, FieldError, JobOpen or DocumentFrozen, and then
    nothing is changed."""
    async with connection.transaction():
        target = await target_of(connection, DOCUMENT_OF_STATEMENT, reader, statement_id)
        if target is None:
            return None
        form = await form_for(connection, target.sector)
        values = checked(STATEMENT_FIELDS, form, given)
        drafts = None if anchors is None else await _anchor_drafts(connection, target.document_id, anchors)
        await guard(connection, target.document_id)
        row = await row_of(connection, _STATEMENT, statement_id)
        if row is None:  # taken away meanwhile
            return None
        details = row.pop("details")
        current = check_revision(row, revision) | {name: details.get(name) for name in WORDING_FIELDS}
        merged = current | values
        merged["addressees"] = sorted(merged["addressees"])
        check_under(form, merged, given=values)
        if merged == current and drafts is None:
            return revision
        kept = {name: value for name, value in details.items() if name not in WORDING_FIELDS}
        changed = [column for key, column in _COLUMNS.items() if merged[key] != current[key]]
        if any(merged[name] != current[name] for name in WORDING_FIELDS):
            changed.append("details = %(details)s")
        cursor = await connection.execute(
            edit_query("statement", changed),
            merged
            | {
                "id": statement_id,
                "details": Jsonb(
                    kept | {name: merged[name] for name in WORDING_FIELDS if merged[name] is not None}
                ),
                "hash": text_hash(str(merged["verbatim"])),
                "obligations": CV + "Obligations",
                "human": HUMAN,
                "proposed": PROPOSED,
            },
        )
        if merged["addressees"] != current["addressees"]:
            await _set_addressees(connection, statement_id, merged["addressees"])
        if drafts is not None:
            await _set_anchors(connection, target.document_id, statement_id, drafts)
        elif merged["verbatim"] != current["verbatim"]:
            await leave_unchecked(connection, "a.statement_id", statement_id)
        await mark_edited(connection, target.document_id)
        return await returned_revision(cursor)


async def add_statement(
    connection: psycopg.AsyncConnection,
    reader: Reader,
    node_id: UUID,
    given: Mapping[str, object],
    anchors: Sequence[HandAnchor],
) -> UUID | None:
    """A new statement of the fields ``given`` and ``anchors`` - one at least - at the node, after its
    others, an editor's proposal; its id. None where ``reader`` sees no such node. FieldError (a field the
    form asks for missing too), JobOpen or DocumentFrozen."""
    async with connection.transaction():
        target = await target_of(connection, DOCUMENT_OF_NODE, reader, node_id)
        if target is None:
            return None
        form = await form_for(connection, target.sector)
        values = checked(STATEMENT_FIELDS, form, every_field(STATEMENT_FIELDS, given))
        check_under(form, values, given=values)
        drafts = await _anchor_drafts(connection, target.document_id, anchors)
        await guard(connection, target.document_id)
        cursor = await connection.execute(
            "SELECT coalesce(max(s.position), 0) + 1 FROM node n LEFT JOIN statement s ON s.node_id = n.id"
            " WHERE n.id = %s GROUP BY n.id",
            (node_id,),
        )
        place = await cursor.fetchone()
        if place is None:  # dropped meanwhile
            return None
        addressees = values["addressees"]
        assert isinstance(addressees, list)  # noqa: S101 - a field of many, by the form's registry
        draft = StatementDraft(
            verbatim=str(values["verbatim"]),
            kind=str(values["statement_kind"]),
            addressees=tuple(addressees),
            anchors=tuple(drafts),
            origin=HUMAN,
            review_status=PROPOSED,
            lead_in=text(values["lead_in"]),
            subkind=text(values["subkind"]),
            obligation=text(values["obligation"]),
            details={name: values[name] for name in WORDING_FIELDS if values[name] is not None},
        )
        [made] = await append_statements(
            connection, target.document_id, node_id, [draft], first_position=int(place[0])
        )
        await mark_edited(connection, target.document_id)
        return made


async def drop_or_reject_statement(
    connection: psycopg.AsyncConnection, reader: Reader, statement_id: UUID, revision: int
) -> Literal["deleted", "rejected"] | None:
    """Take the statement away on its revision ``revision``: delete it where an editor wrote it - an
    editor's from the first, no run's -, with the findings on it and its anchors; else reject it, where
    it is not so already. Which was done; None where ``reader`` sees no such statement. StaleRevision,
    JobOpen or DocumentFrozen, and then nothing is changed."""
    async with connection.transaction():
        target = await target_of(connection, DOCUMENT_OF_STATEMENT, reader, statement_id)
        if target is None:
            return None
        await guard(connection, target.document_id)
        cursor = await connection.execute(_TAKEN, (HUMAN, REJECTED, statement_id))
        found = await cursor.fetchone()
        if found is None:
            return None
        current, by_hand, rejected, anchors = found
        check_revision({"revision": current}, revision)
        if by_hand:
            await drop_findings(connection, target.document_id, [statement_id, *anchors])
            await connection.execute("DELETE FROM statement WHERE id = %s", (statement_id,))
        elif not rejected:
            await connection.execute(
                "UPDATE statement SET review_status_iri = %s, revision = revision + 1, updated_at = now()"
                " WHERE id = %s",
                (REJECTED, statement_id),
            )
        else:
            return "rejected"
        await mark_edited(connection, target.document_id)
        return "deleted" if by_hand else "rejected"


async def _anchor_drafts(
    connection: psycopg.AsyncConnection, document_id: UUID, anchors: Sequence[HandAnchor]
) -> list[AnchorDraft]:
    """The anchors an editor gives, as the store writes them; FieldError ``anchors`` for none, a block of
    no conversion of the document, or a passage found nowhere without a page of the document's."""
    if not anchors:
        raise FieldError("anchors", "required")
    drafts = []
    pages: int | None = None  # the conversion's, read once a passage found nowhere asks
    for anchor in anchors:
        if not anchor.blocks:
            if pages is None:
                cursor = await connection.execute(_CONVERSION_PAGES, (document_id,))
                pages = int(found[0]) if (found := await cursor.fetchone()) is not None else 0
            if anchor.page is None or not 1 <= anchor.page <= pages:
                raise FieldError("anchors", "no_page")
            drafts.append(AnchorDraft(block_ids=(), page_start=anchor.page, match_kind=MATCH_NOT_FOUND))
            continue
        blocks = tuple(dict.fromkeys(anchor.blocks))
        cursor = await connection.execute(_PAGES, (document_id, list(blocks)))
        found = await cursor.fetchone()
        if found is None or found[0] != len(blocks):
            raise FieldError("anchors", "unknown_block")
        first, last = found[1], found[2]
        drafts.append(
            AnchorDraft(block_ids=blocks, page_start=first, page_end=last if last > first else None)
        )
    return drafts


async def _set_addressees(connection: psycopg.AsyncConnection, statement_id: UUID, addressees: Any) -> None:
    await connection.execute("DELETE FROM statement_addressee WHERE statement_id = %s", (statement_id,))
    async with connection.cursor() as cursor:
        await cursor.executemany(
            "INSERT INTO statement_addressee (statement_id, addressee_scheme, addressee_iri)"
            " VALUES (%s, %s, %s)",
            [(statement_id, CV + "Addressees", addressee) for addressee in addressees],
        )


async def _set_anchors(
    connection: psycopg.AsyncConnection, document_id: UUID, statement_id: UUID, drafts: Sequence[AnchorDraft]
) -> None:
    """The statement's anchors ``drafts`` in place of those it had, whose findings go."""
    cursor = await connection.execute(
        "DELETE FROM anchor WHERE statement_id = %s RETURNING id, conversion_id", (statement_id,)
    )
    gone = await cursor.fetchall()
    await drop_findings(connection, document_id, [found for found, _ in gone])
    cursor = await connection.execute("SELECT conversion_id FROM document WHERE id = %s", (document_id,))
    conversion = await cursor.fetchone()
    assert conversion is not None  # noqa: S101 - the document of a statement that stands
    for draft in drafts:
        await write_anchor(connection, document_id, conversion[0], draft, statement_id=statement_id)
