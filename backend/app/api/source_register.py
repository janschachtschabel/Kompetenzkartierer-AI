"""Reading and keeping the source register (plan M1, 1.9 and 1.10).

Who sees which entry is decided in SQL (app/db/source_queries.py): another account's upload is the
404 of an entry that does not exist. Visitors read no register. Editors set an entry's terms of use;
its owner describes it. The file of an entry of no account goes, beside its editors, to whom
THIRD_PARTY_MARKDOWN names (visitors only where PUBLIC_ACCESS is not off); it goes out as a
download in pieces, never to be shown in the browser.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints

from app.api.deps import principal, require_account
from app.api.downloads import ObjectDownload
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.sources import MAX_TITLE_SIGNS, SourceFileOut
from app.core.auth import Principal, one_spelling, shows_whole, visible_only
from app.core.logging import current_request_id
from app.core.storage import ObjectNotFound
from app.db.accounts import record_audit
from app.db.source_queries import Filters, Reader, get_source, list_sources, ownerless_source
from app.db.sources import sector_by_notation, update_source
from app.sources.register import EDUCATION_SECTORS, Provenance, RegisterStatus, RightsStatus, SourceType

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["sources"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Country = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}(-[A-Z0-9]{1,3})?$")]
EDITORS = frozenset({"redaktion", "admin"})
# What only editors set: on what terms the document may be used, and who publishes it
TERMS = frozenset({"rights_status", "rights_evidence", "source_type", "license"})
# The terms whose new values the audit log keeps
AUDITED_VALUES = ("rights_status", "source_type", "license")


# Text in one spelling, showing whole (no control or hidden signs), within its length. Named
# after the constraints, so they wrap them (as in app/api/accounts.py): one spelling first, then
# the spaces go, then the length counts
OneSpelling, ShowsWhole = BeforeValidator(one_spelling), AfterValidator(shows_whole)
TitleText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_SIGNS),
    OneSpelling,
    ShowsWhole,
]
LicenseText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), OneSpelling, ShowsWhole
]
EvidenceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000), OneSpelling, ShowsWhole
]


def _shown(value: object) -> object:
    return visible_only(value) if isinstance(value, str) else value


# A search term is cleaned, not refused, as a file's name is: pasted from a document it may hold
# a no-break space or a soft hyphen. One spelling, no hidden signs, any space a plain one
SearchText = Annotated[str, StringConstraints(max_length=200), BeforeValidator(_shown)]
# Past this a page is no page of a register: a larger offset only makes the database count
MAX_OFFSET = 1_000_000


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


class SourceChange(BaseModel):
    """The fields to change; a field left out stays as it is."""

    model_config = ConfigDict(extra="forbid")

    title: TitleText | None = None
    country: Country | None = None
    sector: Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{1,40}$")] | None = None  # its notation
    license: LicenseText | None = None
    source_type: SourceType | None = None
    rights_status: RightsStatus | None = None
    rights_evidence: EvidenceText | None = None


@router.get("/sources", summary="The register's entries the caller sees, newest first")
async def list_register(
    request: Request,
    who: Account,
    status: Annotated[RegisterStatus | None, Query()] = None,
    provenance: Annotated[Provenance | None, Query()] = None,
    country: Annotated[Country | None, Query()] = None,
    q: Annotated[SearchText | None, Query(description="in the title or the address")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
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
    return SourceDetail.model_validate(_detail(*found, who))


def _detail(row: dict[str, Any], acquisitions: list[Any], who: Principal) -> dict[str, Any]:
    return {
        **_fields(row, who),
        "license": row["license"],
        "rights_evidence": row["rights_evidence"],
        "acquisitions": [acquisition.__dict__ for acquisition in acquisitions],
    }


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


@router.patch("/sources/{source_id}", summary="Change an entry: its description, or (editors) its terms")
async def edit_register_entry(
    source_id: UUID, body: SourceChange, request: Request, who: Account
) -> SourceDetail:
    given = body.model_dump(exclude_unset=True)
    if not given:
        raise Refusal(422, "nothing_to_change", "The change names no field.")
    if "title" in given and given["title"] is None:
        raise Refusal(422, "title_missing", "An entry keeps a title.")
    if "rights_status" in given and given["rights_status"] is None:
        raise Refusal(422, "rights_status_missing", "An entry keeps a rights status, unklar at least.")
    editor = bool(who.roles & EDITORS)
    async with request.app.state.pool.connection() as connection, connection.transaction():
        # locked: two changes at once would each check the terms against the entry before either
        found = await get_source(connection, _reader(who), source_id, for_update=True)
        if found is None:
            raise HTTPException(404, "No such register entry.")
        row, _ = found
        if not editor and row["owner_id"] != who.account_id:
            raise HTTPException(403, "Only the editors change an entry that is not yours.")
        if not editor and TERMS & given.keys():
            raise HTTPException(403, "Only the editors set the terms of use.")
        _check_terms(given, row)
        changes = {name: value for name, value in given.items() if name != "sector"}
        if "sector" in given:
            changes |= await _sector(connection, given["sector"])
        await update_source(connection, source_id, changes)
        # the new terms by value, the evidence by name only: its text may quote anyone
        details = {"fields": sorted(given), **{name: given[name] for name in AUDITED_VALUES if name in given}}
        await record_audit(
            connection,
            who.account_id,
            who.name,
            "source.edit",
            f"source:{source_id}",
            details,
            current_request_id(),
        )
        changed = await get_source(connection, _reader(who), source_id)
    assert changed is not None  # noqa: S101 - changed in this transaction
    return SourceDetail.model_validate(_detail(*changed, who))


def _check_terms(given: dict[str, Any], row: dict[str, Any]) -> None:
    """The terms the entry would have after the change hold together, whichever of them the
    change names: a rights status other than ``unklar`` stands on its evidence - a new one on
    evidence of its own, sent with it -, and ``offen_lizenziert`` names its licence."""
    status = given.get("rights_status", row["rights_status"])
    evidence = given["rights_evidence"] if "rights_evidence" in given else row["rights_evidence"]
    licence = given["license"] if "license" in given else row["license"]
    if status != "unklar" and not (evidence or "").strip():
        raise Refusal(422, "evidence_missing", "A rights status needs its evidence.")
    if status not in ("unklar", row["rights_status"]) and "rights_evidence" not in given:
        raise Refusal(422, "evidence_missing", "A new rights status needs evidence of its own.")
    if status == "offen_lizenziert" and not (licence or "").strip():
        raise Refusal(422, "license_missing", "An open licence names the licence.")


# A response class of no type of its own: each answer names the file's, and the refusals stay JSON
DOWNLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The file, as a download; Content-Type is its own type",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    },
    403: {"model": ErrorBody, "description": "file_hidden: the file of this entry is for its editors only"},
    404: {
        "model": ErrorBody,
        "description": "No such entry for the caller; no_file: it has no file yet; file_gone: the store"
        " lacks it",
    },
}


@router.get(
    "/sources/{source_id}/file",
    summary="The entry's file, as a download",
    status_code=200,  # FastAPI reads it from the response class's signature otherwise
    response_class=ObjectDownload,
    responses=DOWNLOAD_RESPONSES,
)
async def get_register_file(
    source_id: UUID, request: Request, who: Annotated[Principal, Depends(principal)]
) -> ObjectDownload:
    """Its owner and the editors get it; the file of an entry of no account goes, beside them, to
    whom THIRD_PARTY_MARKDOWN names (``hidden``: nobody, ``accounts``, ``public``: visitors too).
    Visitors only where PUBLIC_ACCESS lets them in at all: the stricter rule holds."""
    settings = request.app.state.settings
    opened_to = settings.third_party_markdown
    to_visitors = opened_to == "public" and settings.public_access != "off"
    async with request.app.state.pool.connection() as connection:
        if who.anonymous:
            row = await ownerless_source(connection, source_id) if to_visitors else None
            if row is None:
                raise HTTPException(401, "A token is needed.", headers={"WWW-Authenticate": "Bearer"})
        else:
            found = await get_source(connection, _reader(who), source_id)
            if found is None:
                raise HTTPException(404, "No such register entry.")
            row = found[0]
            own = row["owner_id"] is not None and row["owner_id"] == who.account_id
            if not own and not who.roles & EDITORS and opened_to == "hidden":
                raise Refusal(403, "file_hidden", "The file of this entry is for its editors only.")
    if row["storage_key"] is None:
        raise Refusal(404, "no_file", "The entry has no file yet.")
    try:
        stream = await request.app.state.storage.open_stream(row["storage_key"])
    except ObjectNotFound:
        # the register names a file the store does not hold: lost, or removed by hand
        log.warning("the file of source %s is not in the store: %s", source_id, row["storage_key"])
        raise Refusal(404, "file_gone", "The entry's file is missing from the store.") from None
    headers = {"Content-Disposition": _attachment(row["file_name"]), "Cache-Control": "private, no-store"}
    if stream.size is not None:
        headers["Content-Length"] = str(stream.size)
    return ObjectDownload(stream, media_type=row["mime"], headers=headers)


async def _sector(connection: Any, notation: str | None) -> dict[str, str | None]:
    if notation is None:
        return {"sector_scheme": None, "sector_iri": None}
    iri = await sector_by_notation(connection, notation)
    if iri is None:
        raise Refusal(422, "sector_unknown", "No education sector has this notation.")
    return {"sector_scheme": EDUCATION_SECTORS, "sector_iri": iri}


def _attachment(name: str) -> str:
    """A download under ``name``: a plain ASCII name for old clients, the whole name in UTF-8.

    Without the signs that hide what it is (a right-to-left override), and with no ``%`` in the
    plain name, which some clients read as an escape."""
    shown = visible_only(name)
    plain = "".join(sign if 32 <= ord(sign) < 127 and sign not in '"\\%' else "_" for sign in shown)
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(shown, safe='')}"
