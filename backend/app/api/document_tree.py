"""A document's tree as the editor shows it (plan M1 9.2; app/db/tree.py): its nodes and statements, each
with the fields of the editor's form by their keys (GET /profiles/{sector}/form), its anchors, origin,
review status and revision; each node with the findings on it and its statements counted; the nodes and
statements counted by review status - and whether the caller may edit the tree now and review it, and
where nobody may, why. Read in one snapshot, by who may read the document and its entry's content
(app/api/document_access.py): the statements are that content in the document's words. A node or a
statement alone reads as the tree has it, for the answer to its change.

Editing is the owner's and the editors' (Redaktion, Admin), reviewing the editors' alone; neither while
a job of the document waits or runs (its extraction, repair or check), nor once it is frozen, nor before
its extraction has read every package (X4).
"""

from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import require_account
from app.api.document_access import readable_content, reader, visible_document
from app.api.document_findings import SeverityCounts
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.source_content import EDITORS
from app.core.auth import Principal
from app.db.editing import DOCUMENT_OF_NODE, extracted, target_of
from app.db.statement_editing import DOCUMENT_OF_STATEMENT
from app.db.tree import TreeAnchor, TreeNode, TreeStatement, read_tree, review_counts, walk
from app.domain.l1 import WORDING_FIELDS
from app.jobs.queue import open_job
from app.pipeline.extraction import unique_key
from app.vocab.form_values import FieldValue

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]


class AnchorOut(BaseModel):
    id: UUID
    page_start: int | None  # physical, from 1
    page_end: int | None
    printed_page: str | None  # as the document prints it
    quote: str | None  # the passage found
    match_kind: str | None  # how it was found (cv:MatchKinds); none before X5 looked
    match_score: float | None
    blocks: list[str]  # in the document's order


class StatementOut(BaseModel):
    id: UUID
    position: int
    fields: dict[str, FieldValue]  # by the keys of the form's statement fields, each of them
    origin: str
    review_status: str
    revision: int  # the change of the statement an edit of it names
    iri: str | None  # given when its document was frozen (<node>/s-<n>); a draft copy's rows bring theirs
    text_hash: str
    by_hand: bool  # an editor's own from the first: taking it away deletes it, a run's is rejected
    anchors: list[AnchorOut]


class NodeRowOut(BaseModel):
    """A node itself, without what stands under it."""

    id: UUID
    position: int
    fields: dict[str, FieldValue]  # by the keys of the form's node fields, each of them
    code_assigned: bool  # its code is its position, the source names none
    origin: str
    review_status: str
    revision: int
    iri: str | None  # given when its document was frozen (the path of its codes); a draft copy's bring theirs
    findings: SeverityCounts  # on the node and its anchors, its statements and theirs - not its children's
    anchors: list[AnchorOut]


class NodeOut(NodeRowOut):
    statements: list[StatementOut]
    children: list["NodeOut"]


class ReviewCountsOut(BaseModel):
    nodes: dict[str, int]  # by review status (cv:ReviewStatuses), each of them
    statements: dict[str, int]


Closed = Literal["frozen", "job_open", "not_extracted"]


class TreeOut(BaseModel):
    editable: bool  # the caller may edit the nodes and statements now
    reviewable: bool  # the caller may set their review status now
    closed: Closed | None  # why nobody may now, whoever reads (_closed)
    counts: ReviewCountsOut
    nodes: list[NodeOut]  # from the top, in their order


@router.get(
    "/documents/{document_id}/tree",
    summary="The document's nodes and statements as the editor shows them",
    responses={
        403: {
            "model": ErrorBody,
            "description": "file_hidden: the entry's content is no longer yours to read",
        },
        404: {"model": ErrorBody, "description": "no_document: none the caller may read"},
    },
)
async def read_document_tree(document_id: UUID, request: Request, who: Account) -> TreeOut:
    async with request.app.state.pool.connection() as connection, connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        document = await visible_document(connection, who, document_id)
        await readable_content(connection, who, request.app.state.settings, document)
        tree = await read_tree(connection, reader(who), document_id)
        job = await open_job(connection, unique_key(document_id))
        all_there = await extracted(connection, document_id)
    if tree is None:  # seen in the same snapshot as the document: never so
        raise Refusal(404, "no_document", "No such document.")
    editor = bool(who.roles & EDITORS)
    closed = _closed(frozen=document.frozen_at is not None, job_open=job is not None, extracted=all_there)
    nodes, statements = review_counts(tree)
    return TreeOut(
        editable=closed is None and (editor or document.owner_id == who.account_id),
        reviewable=closed is None and editor,
        closed=closed,
        counts=ReviewCountsOut(nodes=nodes, statements=statements),
        nodes=[_node(node) for node in tree],
    )


def _closed(*, frozen: bool, job_open: bool, extracted: bool) -> Closed | None:
    """Why the tree is closed to change, the reason that lasts longest first: frozen stays, a job ends
    soon - and may be the extraction that has yet to read every package."""
    if frozen:
        return "frozen"
    if job_open:
        return "job_open"
    return None if extracted else "not_extracted"


async def node_as_read(
    connection: psycopg.AsyncConnection, who: Principal, node_id: UUID
) -> NodeRowOut | None:
    """The node as the tree has it, where the caller sees it.

    simplify: reads its document's whole tree for the one row - a change is an editor's, one at a time;
    a read of one row's parts would spare it."""
    found = await _tree_of(connection, who, DOCUMENT_OF_NODE, node_id)
    node = next((node for node in walk(found) if node.id == node_id), None)
    return None if node is None else NodeRowOut(**_node_parts(node))


async def statement_as_read(
    connection: psycopg.AsyncConnection, who: Principal, statement_id: UUID
) -> StatementOut | None:
    """The statement as the tree has it, where the caller sees it (as ``node_as_read``)."""
    found = await _tree_of(connection, who, DOCUMENT_OF_STATEMENT, statement_id)
    said = (said for node in walk(found) for said in node.statements if said.id == statement_id)
    statement = next(said, None)
    return None if statement is None else _statement(statement)


async def _tree_of(
    connection: psycopg.AsyncConnection, who: Principal, query: str, row_id: UUID
) -> tuple[TreeNode, ...]:
    target = await target_of(connection, query, reader(who), row_id)
    if target is None:
        return ()
    return await read_tree(connection, reader(who), target.document_id) or ()


def _node(node: TreeNode) -> NodeOut:
    return NodeOut(
        **_node_parts(node),
        statements=[_statement(statement) for statement in node.statements],
        children=[_node(child) for child in node.children],
    )


def _node_parts(node: TreeNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "position": node.position,
        "fields": {
            "original_title": node.original_title,
            "function": node.function_iri,
            "node_type": node.node_type_iri,
            "code": node.code,
            "obligation": node.obligation_iri,
        },
        "code_assigned": node.code_assigned,
        "origin": node.origin_iri,
        "review_status": node.review_status_iri,
        "revision": node.revision,
        "iri": node.iri,
        "findings": SeverityCounts(**node.findings),
        "anchors": [_anchor(anchor) for anchor in node.anchors],
    }


def _statement(statement: TreeStatement) -> StatementOut:
    return StatementOut(
        id=statement.id,
        position=statement.position,
        fields={
            "verbatim": statement.verbatim,
            "lead_in": statement.lead_in,
            "statement_kind": statement.statement_kind_iri,
            "subkind": statement.subkind_iri,
            "addressees": list(statement.addressees),
            "obligation": statement.obligation_iri,
            **{name: statement.wording.get(name) for name in WORDING_FIELDS},
        },
        origin=statement.origin_iri,
        review_status=statement.review_status_iri,
        revision=statement.revision,
        iri=statement.iri,
        text_hash=statement.text_hash,
        by_hand=statement.by_hand,
        anchors=[_anchor(anchor) for anchor in statement.anchors],
    )


def _anchor(anchor: TreeAnchor) -> AnchorOut:
    return AnchorOut(
        id=anchor.id,
        page_start=anchor.page_start,
        page_end=anchor.page_end,
        printed_page=anchor.printed_page,
        quote=anchor.quote,
        match_kind=anchor.match_kind_iri,
        match_score=anchor.match_score,
        blocks=list(anchor.blocks),
    )
