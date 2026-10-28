"""An editor's changes to a document's first layer (plan M1 9.3, 9.4; Paket 9 G2-G7): a node's fields set,
a node added after its siblings, a node dropped with its subtree - here; a statement's in
app/db/statement_editing.py. Fields go by the keys of the editor's form and are checked against it
(app/vocab/form_values.py).

Every change holds the tree's lock first (``lock_tree``), then refuses a document frozen, one a job
waits or runs on (its extraction, repair or check) and one whose extraction has not read every package
yet (X4: it still writes at the nodes of the open ones, at positions of its own): so no stage writes beside
an editor, and a start between the check and the write waits for the lock, as the job starters take it
too. A change of a row names the revision
it was made on (StaleRevision where the row stands at another) and counts one up; it makes the row an
editor's proposal - its origin the editor's, its rule's name gone, its review status proposed - and
notes the document edited (``document.edited_at``), which owes X5 a check. A change that changes no field
leaves the row as it was. Dropped rows take the findings on them along; their entities stay.

simplify: who sees a document edits it - its owner and the editors (Redaktion, Admin), as
DOCUMENT_VISIBLE has it in M1; once others may read documents (M5), editing needs its own check.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.db.documents import DOCUMENT_VISIBLE, DocumentError
from app.db.nodes import lock_tree, write_subtree
from app.db.runs import done_stages
from app.db.source_queries import Reader
from app.domain.l1 import NodeDraft
from app.jobs.queue import open_job
from app.pipeline.extraction import unique_key
from app.vocab.form_values import FieldValue, check_under, checked
from app.vocab.forms import NODE_FIELDS, Form, FormField, form_of

CV = "https://w3id.org/wlo/curriculum/vocab#"
HUMAN, PROPOSED = CV + "orig_human", CV + "rev_proposed"
SECTOR = "JOIN vocab_concept sector ON sector.iri = d.sector_iri"  # the document's, for its form
DOCUMENT_OF_NODE = f"""
SELECT d.id, sector.notation FROM node n JOIN document d ON d.id = n.document_id {SECTOR}
WHERE n.id = %(id)s AND {DOCUMENT_VISIBLE}
"""  # noqa: S608 - fixed parts
_DOCUMENT = (
    f"SELECT d.id, sector.notation FROM document d {SECTOR} WHERE d.id = %(id)s AND {DOCUMENT_VISIBLE}"  # noqa: S608
)
_NODE = """
SELECT revision, original_title, function_iri AS function, node_type_iri AS node_type, code,
    obligation_iri AS obligation
FROM node WHERE id = %s FOR UPDATE
"""
_EDIT_NODE = """
UPDATE node SET original_title = %(original_title)s, function_iri = %(function)s,
    node_type_iri = %(node_type)s,
    code_assigned = code_assigned AND code IS NOT DISTINCT FROM %(code)s, code = %(code)s,
    obligation_scheme = CASE WHEN %(obligation)s::text IS NULL THEN NULL ELSE %(obligations)s END,
    obligation_iri = %(obligation)s, origin_iri = %(human)s, rule_id = NULL, review_status_iri = %(proposed)s,
    revision = revision + 1, updated_at = now()
WHERE id = %(id)s RETURNING revision
"""
# an anchor of a wording changed, which X5 checks again; one without blocks found no passage, and stays so
_UNCHECKED = """
UPDATE anchor a SET match_kind_scheme = NULL, match_kind_iri = NULL, match_score = NULL, quote = NULL,
    char_start = NULL, char_end = NULL
WHERE {column} = %s AND EXISTS (SELECT FROM anchor_block ab WHERE ab.anchor_id = a.id)
"""
_SUBTREE = """
WITH RECURSIVE under (id) AS (
    SELECT id FROM node WHERE id = %(id)s
    UNION ALL SELECT n.id FROM node n JOIN under u ON n.parent_id = u.id
), said AS (SELECT s.id FROM statement s JOIN under u ON s.node_id = u.id)
SELECT array(SELECT id FROM under), array(SELECT id FROM said),
    array(SELECT a.id FROM anchor a
          WHERE a.node_id IN (SELECT id FROM under) OR a.statement_id IN (SELECT id FROM said))
"""


class JobOpen(Exception):
    """A job of the document waits or runs: no editor changes it meanwhile."""

    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"the job {job_id} of the document waits or runs")
        self.job_id = job_id


class DocumentFrozen(Exception):
    """The document is frozen: its draft copy takes changes (plan M1 9.6)."""


class NotExtracted(Exception):
    """The document's extraction has not read every work package yet (X4): it goes on first."""


class StaleRevision(Exception):
    """The row stands at another revision than the change was made on - ``current``."""

    def __init__(self, current: int) -> None:
        super().__init__(f"the row stands at revision {current}")
        self.current = current


@dataclass(frozen=True)
class Target:
    """The document a change is made in, and the notation of its sector - whose form it takes."""

    document_id: UUID
    sector: str


@dataclass(frozen=True)
class Dropped:
    nodes: int  # the node and its subtree's
    statements: int


async def edit_node(
    connection: psycopg.AsyncConnection,
    reader: Reader,
    node_id: UUID,
    revision: int,
    given: Mapping[str, object],
) -> int | None:
    """Set the node's fields ``given`` by the form's keys, on its revision ``revision``; its revision after,
    None where ``reader`` sees no such node. A new title leaves the anchors of the node for X5 to check
    anew. StaleRevision, FieldError, JobOpen or DocumentFrozen, and then nothing is changed."""
    async with connection.transaction():
        target = await target_of(connection, DOCUMENT_OF_NODE, reader, node_id)
        if target is None:
            return None
        form = await form_for(connection, target.sector)
        values = checked(NODE_FIELDS, form, given)
        await guard(connection, target.document_id)
        row = await row_of(connection, _NODE, node_id)
        if row is None:  # dropped meanwhile
            return None
        current = check_revision(row, revision)
        merged = current | values
        check_under(form, merged, given=values)
        if merged == current:
            return revision
        cursor = await connection.execute(
            _EDIT_NODE,
            merged | {"id": node_id, "obligations": CV + "Obligations", "human": HUMAN, "proposed": PROPOSED},
        )
        if merged["original_title"] != current["original_title"]:
            await leave_unchecked(connection, "a.node_id", node_id)
        await mark_edited(connection, target.document_id)
        return await returned_revision(cursor)


async def add_node(
    connection: psycopg.AsyncConnection,
    reader: Reader,
    document_id: UUID,
    parent_id: UUID | None,
    given: Mapping[str, object],
) -> UUID | None:
    """A new node of the fields ``given`` under ``parent_id`` - the document's top where None -, after the
    siblings there, an editor's proposal; its id. None where ``reader`` sees no such document, or the
    parent is no node of it. FieldError (a field the form asks for missing too), JobOpen, DocumentFrozen."""
    async with connection.transaction():
        target = await target_of(connection, _DOCUMENT, reader, document_id)
        if target is None:
            return None
        form = await form_for(connection, target.sector)
        values = checked(NODE_FIELDS, form, every_field(NODE_FIELDS, given))
        check_under(form, values, given=values)
        await guard(connection, document_id)
        if (
            parent_id is not None
            and await target_of(connection, DOCUMENT_OF_NODE, reader, parent_id) != target
        ):
            return None
        draft = NodeDraft(
            function=str(values["function"]),
            origin=HUMAN,
            review_status=PROPOSED,
            node_type=text(values["node_type"]),
            code=text(values["code"]),
            original_title=text(values["original_title"]),
            obligation=text(values["obligation"]),
        )
        made = await write_subtree(connection, document_id, draft, parent_id=parent_id)
        await mark_edited(connection, document_id)
        return made


async def drop_node(
    connection: psycopg.AsyncConnection, reader: Reader, node_id: UUID, revision: int
) -> Dropped | None:
    """Take the node away with its subtree - its children, statements and the anchors of all - and the
    findings on them; what went. None where ``reader`` sees no such node. StaleRevision, JobOpen or
    DocumentFrozen, and then nothing goes."""
    async with connection.transaction():
        target = await target_of(connection, DOCUMENT_OF_NODE, reader, node_id)
        if target is None:
            return None
        await guard(connection, target.document_id)
        row = await row_of(connection, _NODE, node_id)
        if row is None:
            return None
        check_revision(row, revision)
        cursor = await connection.execute(_SUBTREE, {"id": node_id})
        found = await cursor.fetchone()
        assert found is not None  # noqa: S101 - arrays of a node that stands
        nodes, statements, anchors = found
        await drop_findings(connection, target.document_id, [*nodes, *statements, *anchors])
        await connection.execute("DELETE FROM node WHERE id = %s", (node_id,))
        await mark_edited(connection, target.document_id)
        return Dropped(nodes=len(nodes), statements=len(statements))


async def target_of(
    connection: psycopg.AsyncConnection, query: str, reader: Reader, row_id: UUID
) -> Target | None:
    """The document of the row ``row_id`` by ``query``, where ``reader`` sees it."""
    cursor = await connection.execute(query, {"id": row_id, "me": reader.account_id, "all": reader.sees_all})
    found = await cursor.fetchone()
    return None if found is None else Target(found[0], found[1])


async def form_for(connection: psycopg.AsyncConnection, sector: str) -> Form:
    """The form of the sector's documents; DocumentError ``no_form`` where the sector has no profile."""
    form = await form_of(connection, sector)
    if form is None:
        raise DocumentError(f"no form for documents of the sector {sector!r}", "no_form")
    return form


def every_field(fields: Sequence[FormField], given: Mapping[str, object]) -> dict[str, object]:
    """``given`` with each field it leaves out empty - for a new row, which the form asks the whole of."""
    return {field.key: [] if field.many else None for field in fields} | dict(given)


def text(value: FieldValue) -> str | None:
    """A field's value of one, as a draft takes it."""
    assert not isinstance(value, list)  # noqa: S101 - a field of one, by the form's registry
    return value


async def guard(connection: psycopg.AsyncConnection, document_id: UUID) -> None:
    """Hold the tree's lock, then refuse the change of a frozen document, one beside its open job and one
    X4 has not done yet."""
    await lock_tree(connection, document_id)
    cursor = await connection.execute(
        "SELECT frozen_at IS NOT NULL FROM document WHERE id = %s", (document_id,)
    )
    frozen = await cursor.fetchone()
    if frozen is None:
        raise DocumentError(f"no document {document_id}")
    if frozen[0]:
        raise DocumentFrozen(f"the document {document_id} is frozen")
    if (job := await open_job(connection, unique_key(document_id))) is not None:
        raise JobOpen(job)
    if "X4" not in await done_stages(connection, document_id):
        raise NotExtracted(f"X4 has not read every package of the document {document_id}")


def check_revision(row: dict[str, Any], revision: int) -> dict[str, Any]:
    """The row's fields but its revision; StaleRevision where it stands at another than ``revision``."""
    if row["revision"] != revision:
        raise StaleRevision(row["revision"])
    return {key: value for key, value in row.items() if key != "revision"}


async def leave_unchecked(connection: psycopg.AsyncConnection, column: str, row_id: UUID) -> None:
    """The anchors of the row - ``column`` its node's or statement's - with blocks, for X5 to check anew."""
    assert column in ("a.node_id", "a.statement_id")  # noqa: S101 - the module's own names
    await connection.execute(_UNCHECKED.format(column=column), (row_id,))


async def drop_findings(
    connection: psycopg.AsyncConnection, document_id: UUID, focus: Sequence[UUID]
) -> None:
    """The findings on the rows ``focus``, which go."""
    await connection.execute(
        "DELETE FROM validation_finding WHERE document_id = %s AND focus_id = ANY(%s)",
        (document_id, list(focus)),
    )


async def mark_edited(connection: psycopg.AsyncConnection, document_id: UUID) -> None:
    await connection.execute("UPDATE document SET edited_at = now() WHERE id = %s", (document_id,))


async def row_of(connection: psycopg.AsyncConnection, query: str, row_id: UUID) -> dict[str, Any] | None:
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, (row_id,))
        return await cursor.fetchone()


async def returned_revision(cursor: psycopg.AsyncCursor[Any]) -> int:
    found = await cursor.fetchone()
    assert found is not None  # noqa: S101 - RETURNING of a row that stands
    return int(found[0])
