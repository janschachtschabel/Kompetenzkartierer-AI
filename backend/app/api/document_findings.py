"""A document's findings (plan M1 8b; table validation_finding): what the extraction's stages found on it
- X5's checks, the SHACL gate, the reading of the model's answers - gravest first, each with the kind
and the wording or title of the row it is about, the counts of all beside and at most
``MOST_FINDINGS`` listed. Who may read the document reads them (app/api/document_access.py); its
owner reads too which work packages a repair would ask again (POST /documents/{id}/repair).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import require_account
from app.api.document_access import visible_document
from app.api.errors import AUTH_RESPONSES, ErrorBody
from app.core.auth import Principal
from app.db.findings import findings_of
from app.db.runs import done_stages
from app.domain.l1 import Severity
from app.pipeline.x6_units import repairable_units

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]


class FocusOut(BaseModel):
    kind: str  # the kind of the row: "statement", "node", "document", "frame_part" …
    id: UUID
    label: str | None  # its wording or title, cut to what a list shows; none for a row without


class FindingOut(BaseModel):
    rule: str  # "x5.wording_not_found", "shacl.StatementShape" …
    severity: Severity
    stage: str | None  # the stage whose run found it, "X5"
    focus: FocusOut
    path: str | None  # the property, where it is about one
    message: str
    unit: str | None  # the work package it names, "E2"


class SeverityCounts(BaseModel):
    violation: int
    warning: int
    info: int


class FindingsOut(BaseModel):
    counts: SeverityCounts  # of all the document's findings
    findings: list[FindingOut]
    truncated: bool  # more were found than are listed
    # the work packages a repair would ask again, "E2": to the owner, once X5 has checked the document
    repairable: list[str]


@router.get(
    "/documents/{document_id}/findings",
    summary="The document's findings, gravest first",
    responses={404: {"model": ErrorBody, "description": "no_document: none the caller may read"}},
)
async def read_findings(document_id: UUID, request: Request, who: Account) -> FindingsOut:
    async with request.app.state.pool.connection() as connection:
        document = await visible_document(connection, who, document_id)
        page = await findings_of(connection, document_id)
        repairable: list[str] = []
        if document.owner_id == who.account_id and "X5" in await done_stages(connection, document_id):
            repairable = [unit.package.key for unit in await repairable_units(connection, document_id)]
    return FindingsOut(
        counts=SeverityCounts(**page.counts),
        findings=[
            FindingOut(
                rule=row.rule,
                severity=row.severity,
                stage=row.stage,
                focus=FocusOut(kind=row.focus_kind, id=row.focus_id, label=row.focus_label),
                path=row.path,
                message=row.message,
                unit=row.unit,
            )
            for row in page.rows
        ],
        truncated=page.truncated,
        repairable=repairable,
    )
