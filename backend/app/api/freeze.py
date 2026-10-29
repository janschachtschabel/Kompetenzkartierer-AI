"""A document frozen (plan M1 9.6; Paket 9b H5; app/db/freezing.py): by the editors (Redaktion, Admin)
alone, under the service's IRI base (IRI_BASE). Refused as app/api/edit_answers.py says for a frozen
document, an open job and a tree X4 has not read, and with 409 and its own code where it is not ready:
``incomplete`` (details.missing), ``no_iri_base``, ``not_checked`` (details.unchecked),
``has_violations`` (details.violations; ``accept_violations`` freezes it with them) and ``iri_taken``
(details.iri). Audited with the violations it was frozen with; the answer is the document.
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
from app.db.freezing import FreezeRefused, freeze

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
FREEZE_RESPONSES: Responses = {
    403: {"model": ErrorBody, "description": "not_editor: the editors alone freeze a document"},
    409: {
        "model": ErrorBody,
        "description": "frozen, job_open (details.job_id to the owner and the admins), not_extracted,"
        " incomplete (details.missing), no_iri_base, not_checked (details.unchecked), has_violations"
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
async def freeze_a_document(document_id: UUID, body: FreezeIn, request: Request, who: Account) -> DocumentOut:
    base = request.app.state.settings.iri_base
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                await visible_document(connection, who, document_id)
                if not who.roles & EDITORS:
                    raise Refusal(403, "not_editor", "Only the editors freeze a document.")
                frozen = await freeze(connection, document_id, base, accept_violations=body.accept_violations)
                details = {
                    "revision": frozen.revision,
                    "violations": frozen.violations,
                    "accepted": body.accept_violations and frozen.violations > 0,
                }
                await audit(connection, who, "document.freeze", f"document:{document_id}", details)
        except FreezeRefused as error:
            raise _refusal(error) from error
        except REFUSED as error:
            raise await refusal_of(connection, who, document_id, error) from error
        return await document_out(connection, await visible_document(connection, who, document_id), who)


def _refusal(refused: FreezeRefused) -> Refusal:
    details = refused.details
    match refused.code:
        case "incomplete":
            return Refusal(409, "incomplete", "The document lacks what its IRI is made of.", details=details)
        case "no_iri_base":
            return Refusal(409, "no_iri_base", "The service names no IRI base to freeze under (IRI_BASE).")
        case "not_checked":
            return Refusal(
                409, "not_checked", "X5 owes the document a check: check it again.", details=details
            )
        case "has_violations":
            return Refusal(
                409, "has_violations", "Its findings name violations: accept them.", details=details
            )
        case "iri_taken":
            return Refusal(409, "iri_taken", "Another work or document holds the IRI.", details=details)
        case _:
            assert_never(refused.code)
