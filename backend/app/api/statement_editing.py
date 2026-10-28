"""An editor's changes to a document's statements (plan M1 9.4; app/db/statement_editing.py): a statement's
fields, addressees and anchors set on the revision it was read at, a statement added at the end of a node
with an anchor at least, a statement taken away - rejected where a run wrote it, deleted where an editor
did. By the document's owner and the editors; answered with the statement as the tree has it, refused as
app/api/edit_answers.py says.
"""

from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import require_account
from app.api.document_access import reader
from app.api.document_tree import StatementOut, statement_as_read
from app.api.edit_answers import REFUSED, Fields, answers, audit, refusal_of, stale
from app.api.errors import AUTH_RESPONSES, Refusal
from app.core.auth import Principal
from app.db.editing import DOCUMENT_OF_NODE, StaleRevision, target_of
from app.db.statement_editing import (
    DOCUMENT_OF_STATEMENT,
    HandAnchor,
    add_statement,
    drop_or_reject_statement,
    edit_statement,
)

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Revision = Annotated[int, Query(ge=1, description="The statement's revision as it was read")]
NO_STATEMENT = "no_statement: none the caller may read"
MOST_ANCHORS = 20
MOST_BLOCKS = 200  # of one anchor: a passage over pages of tables
MOST_PAGE = 99_999  # as a block's id counts them (BlockId); the conversion's own pages bound it further
BlockId = Annotated[str, Field(pattern=r"^p[0-9]{1,5}-b[0-9]{1,6}$")]


class AnchorIn(BaseModel):
    """Blocks of the document's conversion where the statement stands - its pages follow from them -, or
    none and the page it stands on, where no block holds it."""

    model_config = ConfigDict(extra="forbid")
    blocks: list[BlockId] = Field(default=[], max_length=MOST_BLOCKS)
    page: int | None = Field(default=None, ge=1, le=MOST_PAGE)


Anchors = Annotated[list[AnchorIn], Field(max_length=MOST_ANCHORS)]


class StatementEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)  # the statement's, as it was read
    fields: Fields  # those to set, by the form's keys; one left out keeps its value
    anchors: Anchors | None = None  # all of them in place of those it has; none: they stay


class NewStatementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: Fields  # by the form's keys, those it asks for among them
    anchors: Anchors = []  # one at least: none is anchor_missing, as an empty list


class TakenOut(BaseModel):
    outcome: Literal["deleted", "rejected"]  # deleted: an editor's own; rejected: a run's, which stays


@router.patch(
    "/statements/{statement_id}",
    summary="Set a statement's fields and anchors - the statement an editor's proposal after",
    responses=answers(NO_STATEMENT),
)
async def edit_a_statement(
    statement_id: UUID, body: StatementEditIn, request: Request, who: Account
) -> StatementOut:
    anchors = None if body.anchors is None else _hand(body.anchors)
    async with request.app.state.pool.connection() as connection:
        document_id: UUID | None = None
        try:
            async with connection.transaction():
                target = await target_of(connection, DOCUMENT_OF_STATEMENT, reader(who), statement_id)
                if target is None:
                    raise Refusal(404, "no_statement", "No such statement.")
                document_id = target.document_id
                revision = await edit_statement(
                    connection,
                    reader(who),
                    statement_id,
                    body.expected_revision,
                    body.fields,
                    anchors=anchors,
                )
                if revision is None:  # taken away meanwhile
                    raise Refusal(404, "no_statement", "No such statement.")
                details = {
                    "document": str(document_id), "revision": revision, "fields": sorted(body.fields),
                    "anchors": None if anchors is None else len(anchors),
                }  # fmt: skip
                await audit(connection, who, "statement.edit", f"statement:{statement_id}", details)
        except StaleRevision as error:
            raise stale("statement", await statement_as_read(connection, who, statement_id)) from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await _read(connection, who, statement_id)


@router.post(
    "/nodes/{node_id}/statements",
    status_code=201,
    summary="Add a statement after the node's others - an editor's proposal",
    responses=answers("no_node: none the caller may read"),
)
async def add_a_statement(
    node_id: UUID, body: NewStatementIn, request: Request, who: Account
) -> StatementOut:
    async with request.app.state.pool.connection() as connection:
        document_id: UUID | None = None
        try:
            async with connection.transaction():
                target = await target_of(connection, DOCUMENT_OF_NODE, reader(who), node_id)
                if target is None:
                    raise Refusal(404, "no_node", "No such node.")
                document_id = target.document_id
                made = await add_statement(connection, reader(who), node_id, body.fields, _hand(body.anchors))
                if made is None:  # taken away meanwhile
                    raise Refusal(404, "no_node", "No such node.")
                details = {"document": str(document_id), "node": str(node_id), "fields": sorted(body.fields)}
                await audit(connection, who, "statement.add", f"statement:{made}", details)
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await _read(connection, who, made)


@router.delete(
    "/statements/{statement_id}",
    summary="Take a statement away: reject a run's, delete an editor's own",
    responses=answers(NO_STATEMENT),
)
async def take_a_statement(
    statement_id: UUID, expected_revision: Revision, request: Request, who: Account
) -> TakenOut:
    async with request.app.state.pool.connection() as connection:
        document_id: UUID | None = None
        try:
            async with connection.transaction():
                target = await target_of(connection, DOCUMENT_OF_STATEMENT, reader(who), statement_id)
                if target is None:
                    raise Refusal(404, "no_statement", "No such statement.")
                document_id = target.document_id
                outcome = await drop_or_reject_statement(
                    connection, reader(who), statement_id, expected_revision
                )
                if outcome is None:
                    raise Refusal(404, "no_statement", "No such statement.")
                action = "statement.delete" if outcome == "deleted" else "statement.reject"
                await audit(
                    connection, who, action, f"statement:{statement_id}", {"document": str(document_id)}
                )
        except StaleRevision as error:
            raise stale("statement", await statement_as_read(connection, who, statement_id)) from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
    return TakenOut(outcome=outcome)


def _hand(anchors: list[AnchorIn]) -> list[HandAnchor]:
    return [HandAnchor(blocks=tuple(anchor.blocks), page=anchor.page) for anchor in anchors]


async def _read(connection: psycopg.AsyncConnection, who: Principal, statement_id: UUID) -> StatementOut:
    read = await statement_as_read(connection, who, statement_id)
    if read is None:  # taken away right after
        raise Refusal(404, "no_statement", "No such statement.")
    return read
