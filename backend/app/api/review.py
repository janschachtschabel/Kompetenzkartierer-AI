"""The editors' review of a document (plan M1 9.5; app/db/review.py): one review status - proposed,
confirmed, rejected - for many of its nodes and statements at once, all or nothing, each on the revision
it was read at. By the editors (Redaktion, Admin) alone, audited; refused as app/api/edit_answers.py says,
a stale row with each that stands otherwise and its revision now.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import require_account
from app.api.document_access import visible_document
from app.api.edit_answers import REFUSED, REVIEW_RESPONSES, answers, audit, refusal_of
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.source_content import EDITORS
from app.core.auth import Principal
from app.db.editing import CV
from app.db.review import ReviewItem, StaleItems, set_review

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
MOST_REVIEWED = 2_000  # rows of one review: a long document's statements


class ReviewItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["node", "statement"]
    id: UUID
    revision: int = Field(ge=1)  # the row's, as it was read


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["proposed", "confirmed", "rejected"]  # of cv:ReviewStatuses, by its rev_ name
    items: list[ReviewItemIn] = Field(min_length=1, max_length=MOST_REVIEWED)


class RevisionOut(BaseModel):
    id: UUID
    revision: int  # after the review; a row at the status already keeps its own


class ReviewOut(BaseModel):
    revisions: list[RevisionOut]  # each row named, once, in the order asked


@router.post(
    "/documents/{document_id}/review",
    summary="Set the review status of nodes and statements at once - the editors alone",
    responses=answers("no_document: none the caller may read", REVIEW_RESPONSES)
    | {403: {"model": ErrorBody, "description": "not_editor: the editors alone review"}},
)
async def review_rows(document_id: UUID, body: ReviewIn, request: Request, who: Account) -> ReviewOut:
    items = [ReviewItem(item.kind, item.id, item.revision) for item in body.items]
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                await visible_document(connection, who, document_id)
                if not who.roles & EDITORS:
                    raise Refusal(403, "not_editor", "Only the editors set a review status.")
                revisions = await set_review(connection, document_id, CV + "rev_" + body.status, items)
                details = {"status": body.status, "items": len(revisions)}
                await audit(connection, who, "review.set", f"document:{document_id}", details)
        except StaleItems as error:
            stale = [{"kind": row.kind, "id": str(row.id), "current": row.current} for row in error.stale]
            raise Refusal(
                409,
                "stale_revision",
                "Rows were changed meanwhile: see them as they stand.",
                details={"stale": stale},
            ) from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
    return ReviewOut(
        revisions=[RevisionOut(id=row, revision=revision) for row, revision in revisions.items()]
    )
