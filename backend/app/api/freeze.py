"""A document frozen and copied as a draft (plan M1 9.6; Paket 9b H5, H7; app/db/freezing.py,
app/db/draft_copy.py), by the editors (Redaktion, Admin) alone.

A document is frozen under the service's IRI base (IRI_BASE). Refused as app/api/edit_answers.py says for
a frozen document, an open job and a tree X4 has not read, and with 409 and its own code where it is not
ready:
``incomplete`` (details.missing), ``no_iri_base``, ``check_owed`` (details.unchecked),
``has_violations`` (details.violations; ``accept_violations`` freezes it with them) and ``iri_taken``
(details.iri). Audited with the violations it was frozen with; the answer is the document.

A frozen document's draft copy is the next revision under its IRI (201, the copy): refused for a draft
(409 ``not_frozen``), a revision a later one follows (``not_latest``) and beside an open draft of the
IRI (``draft_open``, details.document_id). Audited as ``document.copy`` with the copy.
"""

from typing import Annotated, assert_never
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api.deps import require_account
from app.api.document_access import visible_document
from app.api.documents import DocumentOut, document_out
from app.api.edit_answers import REFUSED, Responses, answers, audit, refusal_of
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.source_content import EDITORS
from app.core.auth import Principal
from app.db.documents import DocumentError
from app.db.draft_copy import CopyRefused, copy_document
from app.db.freezing import FreezeRefused, freeze

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
FREEZE_RESPONSES: Responses = {
    403: {"model": ErrorBody, "description": "not_editor: the editors alone freeze a document"},
    409: {
        "model": ErrorBody,
        "description": "frozen, job_open (details.job_id to the owner and the admins), not_extracted,"
        " incomplete (details.missing), no_iri_base, check_owed (details.unchecked), has_violations"
        " (details.violations), iri_taken (details.iri)",
    },
}


class FreezeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accept_violations: bool = False  # freeze it with the violations its findings name


@router.post(
    "/documents/{document_id}/freeze",
    summary="Freeze the document: its IRIs given, it changes no more - the editors alone",
    responses=answers("no_document: none the caller may read", FREEZE_RESPONSES),
)
async def freeze_a_document(
    document_id: UUID, request: Request, who: Account, body: FreezeIn | None = None
) -> DocumentOut:
    base = request.app.state.settings.iri_base
    accept = body is not None and body.accept_violations  # no body: no violations accepted
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                await visible_document(connection, who, document_id)
                if not who.roles & EDITORS:
                    raise Refusal(403, "not_editor", "Only the editors freeze a document.")
                frozen = await freeze(connection, document_id, base, accept_violations=accept)
                details = {
                    "revision": frozen.revision,
                    "violations": frozen.violations,
                    "accepted": accept and frozen.violations > 0,
                }
                await audit(connection, who, "document.freeze", f"document:{document_id}", details)
        except FreezeRefused as error:
            raise _refusal(error) from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await document_out(connection, await visible_document(connection, who, document_id), who)


@router.post(
    "/documents/{document_id}/draft-copy",
    status_code=201,
    summary="Copy the frozen document as a draft: its next revision, under its IRI - the editors alone",
    responses={
        403: {"model": ErrorBody, "description": "not_editor: the editors alone copy a document"},
        404: {"model": ErrorBody, "description": "no_document: none the caller may read"},
        409: {
            "model": ErrorBody,
            "description": "not_frozen, not_latest, draft_open (details.document_id: the draft open),"
            " vocabulary_changed (details.check: the check a row of it fails today)",
        },
    },
)
async def copy_a_document(document_id: UUID, request: Request, who: Account) -> DocumentOut:
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                document = await visible_document(connection, who, document_id)
                if not who.roles & EDITORS:
                    raise Refusal(403, "not_editor", "Only the editors copy a document.")
                copy = await copy_document(connection, document_id)
                details = {"copy": str(copy), "revision": document.revision + 1}
                await audit(connection, who, "document.copy", f"document:{document_id}", details)
        except CopyRefused as error:
            match error.code:
                case "not_frozen":
                    raise Refusal(409, "not_frozen", "A draft is changed as it is.") from error
                case "not_latest":
                    raise Refusal(409, "not_latest", "A later revision is frozen: copy that one.") from error
                case "draft_open":
                    raise Refusal(
                        409, "draft_open", "A draft of this IRI is open.", details=error.details
                    ) from error
                case "vocabulary_changed":
                    raise Refusal(
                        409,
                        "vocabulary_changed",
                        "A row of it no longer fits the vocabularies.",
                        details=error.details,
                    ) from error
                case _:
                    assert_never(error.code)
        except DocumentError as error:  # taken away meanwhile
            raise Refusal(404, "no_document", "No such document.") from error
        return await document_out(connection, await visible_document(connection, who, copy), who)


def _refusal(refused: FreezeRefused) -> Refusal:
    details = refused.details
    match refused.code:
        case "incomplete":
            return Refusal(409, "incomplete", "The document lacks what its IRI is made of.", details=details)
        case "no_iri_base":
            return Refusal(409, "no_iri_base", "The service names no IRI base to freeze under (IRI_BASE).")
        case "check_owed":
            return Refusal(
                409, "check_owed", "X5 owes the document a check: check it again.", details=details
            )
        case "has_violations":
            return Refusal(
                409, "has_violations", "Its findings name violations: accept them.", details=details
            )
        case "iri_taken":
            return Refusal(409, "iri_taken", "Another work or document holds the IRI.", details=details)
        case _:
            assert_never(refused.code)
