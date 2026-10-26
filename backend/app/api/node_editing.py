"""An editor's changes to a document's nodes (plan M1 9.3; app/db/editing.py): a node's fields set on the
revision it was read at, a node added after its siblings - under a node of the document, or at its top -,
a node dropped with its subtree. By the document's owner and the editors; answered with the node as the
tree has it (GET /documents/{id}/tree), refused as app/api/edit_answers.py says - a stale revision with
the node as it stands.
"""

from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import require_account
from app.api.document_access import reader, visible_document
from app.api.document_tree import NodeRowOut, node_as_read
from app.api.edit_answers import REFUSED, Fields, answers, audit, refusal_of, stale
from app.api.errors import AUTH_RESPONSES, Refusal
from app.core.auth import Principal
from app.db.editing import DOCUMENT_OF_NODE, StaleRevision, add_node, drop_node, edit_node, target_of

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Revision = Annotated[int, Query(ge=1, description="The node's revision as it was read")]
NO_NODE = "no_node: none the caller may read"


class NodeEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)  # the node's, as it was read
    fields: Fields  # those to set, by the form's keys; one left out keeps its value


class NewNodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parent_id: UUID | None = None  # a node of the document; none: its top
    fields: Fields  # by the form's keys, those it asks for among them


class DroppedOut(BaseModel):
    nodes: int  # the node and those under it
    statements: int


@router.patch(
    "/nodes/{node_id}",
    summary="Set a node's fields - the node an editor's proposal after",
    responses=answers(NO_NODE),
)
async def edit_a_node(node_id: UUID, body: NodeEditIn, request: Request, who: Account) -> NodeRowOut:
    async with request.app.state.pool.connection() as connection:
        document_id: UUID | None = None
        try:
            async with connection.transaction():
                target = await target_of(connection, DOCUMENT_OF_NODE, reader(who), node_id)
                if target is None:
                    raise Refusal(404, "no_node", "No such node.")
                document_id = target.document_id
                revision = await edit_node(
                    connection, reader(who), node_id, body.expected_revision, body.fields
                )
                if revision is None:  # taken away meanwhile
                    raise Refusal(404, "no_node", "No such node.")
                details = {"document": str(document_id), "revision": revision, "fields": sorted(body.fields)}
                await audit(connection, who, "node.edit", f"node:{node_id}", details)
        except StaleRevision as error:
            raise stale("node", await node_as_read(connection, who, node_id)) from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await _read(connection, who, node_id)


@router.post(
    "/documents/{document_id}/nodes",
    status_code=201,
    summary="Add a node after its siblings - an editor's proposal",
    responses=answers("no_document, no_node: the parent"),
)
async def add_a_node(document_id: UUID, body: NewNodeIn, request: Request, who: Account) -> NodeRowOut:
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                await visible_document(connection, who, document_id)
                made = await add_node(connection, reader(who), document_id, body.parent_id, body.fields)
                if made is None:
                    raise Refusal(404, "no_node", "No such parent node in the document.")
                parent = None if body.parent_id is None else str(body.parent_id)
                details = {"document": str(document_id), "parent": parent, "fields": sorted(body.fields)}
                await audit(connection, who, "node.add", f"node:{made}", details)
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await _read(connection, who, made)


@router.delete(
    "/nodes/{node_id}",
    summary="Take a node away with its subtree and the findings on them",
    responses=answers(NO_NODE),
)
async def drop_a_node(
    node_id: UUID, expected_revision: Revision, request: Request, who: Account
) -> DroppedOut:
    async with request.app.state.pool.connection() as connection:
        document_id: UUID | None = None
        try:
            async with connection.transaction():
                target = await target_of(connection, DOCUMENT_OF_NODE, reader(who), node_id)
                if target is None:
                    raise Refusal(404, "no_node", "No such node.")
                document_id = target.document_id
                dropped = await drop_node(connection, reader(who), node_id, expected_revision)
                if dropped is None:
                    raise Refusal(404, "no_node", "No such node.")
                details = {
                    "document": str(document_id),
                    "nodes": dropped.nodes,
                    "statements": dropped.statements,
                }
                await audit(connection, who, "node.drop", f"node:{node_id}", details)
        except StaleRevision as error:
            raise stale("node", await node_as_read(connection, who, node_id)) from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
    return DroppedOut(nodes=dropped.nodes, statements=dropped.statements)


async def _read(connection: psycopg.AsyncConnection, who: Principal, node_id: UUID) -> NodeRowOut:
    read = await node_as_read(connection, who, node_id)
    if read is None:  # taken away right after
        raise Refusal(404, "no_node", "No such node.")
    return read
