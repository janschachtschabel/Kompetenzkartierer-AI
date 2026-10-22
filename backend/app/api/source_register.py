"""Reading the source register (plan M1, 1.9); editing an entry and fetching its file follow (1.10).

Who sees which entry is decided in SQL (app/db/source_queries.py): another account's upload is the
404 of an entry that does not exist. Visitors read no register.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, StringConstraints

from app.api.deps import require_account
from app.api.errors import AUTH_RESPONSES
from app.api.sources import SourceFileOut
from app.core.auth import Principal
from app.db.source_queries import Filters, Reader, get_source, list_sources
from app.sources.register import Provenance, RegisterStatus, RightsStatus, SourceType

router = APIRouter(prefix="/api/v1", tags=["sources"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")]
EDITORS = frozenset({"redaktion", "admin"})


class SourceEntry(BaseModel):
    id: UUID
    title: str
    provenance: Provenance
    rights_status: RightsStatus
    source_type: SourceType | None
    register_status: RegisterStatus
    country: str | None
    sector: str | None  # a concept of cv:EducationSectors
    url: str | None
    file: SourceFileOut | None
    mine: bool  # the caller's own entry
    created_at: datetime
    updated_at: datetime


class AcquisitionOut(BaseModel):
    method: Literal["upload", "url"]
    acquired_at: datetime
    chain: list[str]
    received_name: str | None


class SourceDetail(SourceEntry):
    license: str | None
    rights_evidence: str | None
    acquisitions: list[AcquisitionOut]


class SourcePage(BaseModel):
    entries: list[SourceEntry]
    total: int
    limit: int
    offset: int


@router.get("/sources", summary="The register's entries the caller sees, newest first")
async def list_register(
    request: Request,
    who: Account,
    status: Annotated[RegisterStatus | None, Query()] = None,
    provenance: Annotated[Provenance | None, Query()] = None,
    country: Annotated[Country | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200, description="in the title or the address")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourcePage:
    filters = Filters(status=status, provenance=provenance, country=country, text=q)
    async with request.app.state.pool.connection() as connection:
        rows, total = await list_sources(connection, _reader(who), filters, limit=limit, offset=offset)
    entries = [SourceEntry.model_validate(_fields(row, who)) for row in rows]
    return SourcePage(entries=entries, total=total, limit=limit, offset=offset)


@router.get("/sources/{source_id}", summary="One entry of the register, with how its file came")
async def get_register_entry(source_id: UUID, request: Request, who: Account) -> SourceDetail:
    async with request.app.state.pool.connection() as connection:
        found = await get_source(connection, _reader(who), source_id)
    if found is None:
        raise HTTPException(404, "No such register entry.")
    row, acquisitions = found
    return SourceDetail.model_validate(
        {
            **_fields(row, who),
            "license": row["license"],
            "rights_evidence": row["rights_evidence"],
            "acquisitions": [acquisition.__dict__ for acquisition in acquisitions],
        }
    )


def _reader(who: Principal) -> Reader:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    return Reader(account_id=who.account_id, sees_all=bool(who.roles & EDITORS))


def _fields(row: dict[str, Any], who: Principal) -> dict[str, Any]:
    file = None
    if row["file_name"] is not None:
        file = {
            "name": row["file_name"],
            "mime": row["mime"],
            "size": row["size_bytes"],
            "sha256": row["sha256"].hex(),
        }
    keep = ("id", "title", "provenance", "rights_status", "source_type", "register_status", "country", "url")
    return {
        **{name: row[name] for name in keep},
        "sector": row["sector_iri"],
        "file": file,
        "mine": row["owner_id"] is not None and row["owner_id"] == who.account_id,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
