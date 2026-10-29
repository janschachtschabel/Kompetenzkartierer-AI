"""A document's work and metadata (plan M1 9.6; Paket 9b H3, H4; app/db/document_meta.py): the editors
(Redaktion, Admin) set its work - one there is, or one made of a title, a country and a short title -,
its owner and the editors its issuer, edition and title. Refused as app/api/edit_answers.py says, a
work there is not with 404 ``no_work``, and what the document's IRI is made of once it has one with 409
``named``. Each audited; the answer is the document.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.deps import require_account
from app.api.document_access import reader, visible_document
from app.api.documents import DocumentOut, document_out
from app.api.edit_answers import REFUSED, Responses, answers, audit, refusal_of
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.source_content import EDITORS
from app.core.auth import Principal
from app.db.document_meta import ExistingWork, NewWork, set_metadata, set_work
from app.db.documents import DocumentError

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
NO_DOCUMENT = "no_document: none the caller may read"
META_RESPONSES: Responses = {
    422: {"model": ErrorBody, "description": "invalid_field (details: field, problem)"},
    409: {
        "model": ErrorBody,
        "description": "job_open (details.job_id to the owner and the admins), frozen, named: the"
        " document's IRI is made of it",
    },
}


class ExistingWorkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_id: UUID


class NewWorkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    region: Annotated[str, Field(pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")]  # ISO 3166: DE, DE-NW
    short_title: Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=200)]  # a slug


class MetadataIn(BaseModel):
    """The metadata to set; one left out stays, null or a blank text empties it."""

    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    issuer: str | None = None
    edition: str | None = None


@router.patch(
    "/documents/{document_id}/work",
    summary="Set the document's work: one there is, or one made - the editors alone",
    responses=answers(NO_DOCUMENT + "; no_work: no such work", META_RESPONSES)
    | {403: {"model": ErrorBody, "description": "not_editor: the editors alone set a work"}},
)
async def set_a_work(
    document_id: UUID, body: ExistingWorkIn | NewWorkIn, request: Request, who: Account
) -> DocumentOut:
    work = ExistingWork(body.work_id) if isinstance(body, ExistingWorkIn) else NewWork(**body.model_dump())
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                await visible_document(connection, who, document_id)
                if not who.roles & EDITORS:
                    raise Refusal(403, "not_editor", "Only the editors set a document's work.")
                work_id = await set_work(connection, reader(who), document_id, work)
                if work_id is None:  # taken away meanwhile
                    raise Refusal(404, "no_document", "No such document.")
                details = {"work": str(work_id), "made": isinstance(work, NewWork)}
                await audit(connection, who, "document.work", f"document:{document_id}", details)
        except DocumentError as error:
            if error.code != "no_work":
                raise await refusal_of(connection, who, document_id, error) from error
            raise Refusal(404, "no_work", "No such work.") from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await document_out(connection, await visible_document(connection, who, document_id), who)


@router.patch(
    "/documents/{document_id}",
    summary="Set the document's issuer, edition or title",
    responses=answers(NO_DOCUMENT, META_RESPONSES),
)
async def set_the_metadata(
    document_id: UUID, body: MetadataIn, request: Request, who: Account
) -> DocumentOut:
    given: dict[str, Any] = body.model_dump(include=body.model_fields_set)
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                changed = await set_metadata(connection, reader(who), document_id, given)
                if changed is None:
                    raise Refusal(404, "no_document", "No such document.")
                if changed:
                    details = {"fields": sorted(given)}
                    await audit(connection, who, "document.edit", f"document:{document_id}", details)
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await document_out(connection, await visible_document(connection, who, document_id), who)
