"""The source register: an account's uploads (plan M1, 1.7); reading and editing follow.

The upload route has no body parameter on purpose: FastAPI reads such a body before it checks
the token, so the form is read here, after it. BodyLimit (app/api/body_limit.py) bounds the body
before anything reads it; the file is counted again as it is read, in pieces of a MiB.
"""

import asyncio
import hashlib
from pathlib import PurePosixPath
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from app.api.deps import require_account
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.core.auth import Principal, plain_text, visible_only
from app.core.logging import current_request_id
from app.db.accounts import record_audit
from app.db.rate_limits import RateLimited, take
from app.db.sources import StoredFile, record_upload
from app.sources.archives import ArchiveTooLarge, ArchiveUnreadable
from app.sources.filetype import MAX_NAME_SIGNS, DetectedType, UnsupportedType, accepted_type, stored_name
from app.sources.register import Provenance, RegisterStatus, RightsStatus

router = APIRouter(prefix="/api/v1", tags=["sources"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
UPLOAD_PATH = "/api/v1/sources"
MIB = 2**20
MAX_TITLE_SIGNS = 500
UPLOAD_REFUSALS: dict[int | str, dict[str, Any]] = {
    413: {"model": ErrorBody, "description": "The file, or the archive it is, is too large"},
    415: {"model": ErrorBody, "description": "No type a conversion reads"},
}


class SourceFileOut(BaseModel):
    name: str
    mime: str
    size: int
    sha256: str


class SourceOut(BaseModel):
    id: UUID
    title: str
    provenance: Provenance
    rights_status: RightsStatus
    register_status: RegisterStatus
    file: SourceFileOut | None


@router.post("/sources", status_code=201, summary="Upload a curriculum document", responses=UPLOAD_REFUSALS)
async def upload_source(request: Request, who: Account) -> SourceOut:
    """A form with ``file`` and, if wished, ``title`` (else the file's name names the entry)."""
    settings = request.app.state.settings
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    async with request.app.state.pool.connection() as connection:
        try:
            await take(connection, who.account_id, "source.upload", per_minute=settings.uploads_per_minute)
        except RateLimited as limited:
            retry = {"Retry-After": str(limited.retry_after_s)}
            raise Refusal(429, "too_many_uploads", "Too many uploads; try again later.", retry) from None
    async with request.form(max_files=1, max_fields=2) as form:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise Refusal(422, "file_missing", "The form holds no file.")
        given_title = form.get("title")
        data = await _read(upload, settings.max_upload_mb * MIB)
        received = upload.filename or ""
    detected, digest = await asyncio.to_thread(_examine, received, data)
    file_name = stored_name(received, detected)
    title = _title(given_title if isinstance(given_title, str) else None, file_name)
    stored = StoredFile(
        sha256=digest, size=len(data), mime=detected.mime, storage_key=f"sources/{digest.hex()}"
    )
    storage = request.app.state.storage
    if not await storage.exists(stored.storage_key):  # the same bytes are stored once
        await storage.put(stored.storage_key, data)
    async with request.app.state.pool.connection() as connection, connection.transaction():
        source_id = await record_upload(
            connection,
            owner=who.account_id,
            stored=stored,
            file_name=file_name,
            received_name=visible_only(received)[:MAX_NAME_SIGNS],
            title=title,
        )
        details = {"sha256": digest.hex(), "size": len(data), "mime": detected.mime}
        await record_audit(
            connection,
            who.account_id,
            who.name,
            "source.upload",
            f"source:{source_id}",
            details,
            current_request_id(),
        )
    return SourceOut(
        id=source_id,
        title=title,
        provenance="upload",
        rights_status="unklar",
        register_status="acquired",
        file=SourceFileOut(name=file_name, mime=detected.mime, size=len(data), sha256=digest.hex()),
    )


async def _read(upload: UploadFile, limit: int) -> bytes:
    """The file's bytes, read a MiB at a time and refused once past ``limit``."""
    received = bytearray()
    while piece := await upload.read(MIB):
        received += piece
        if len(received) > limit:
            raise Refusal(413, "file_too_large", f"The file is larger than {limit // MIB} MB.")
    return bytes(received)


def _examine(name: str, data: bytes) -> tuple[DetectedType, bytes]:
    """Its type and SHA-256; in a thread, as the archive check unpacks and hashing takes a while."""
    try:
        detected = accepted_type(name, data)
    except (UnsupportedType, ArchiveUnreadable):
        raise Refusal(415, "unsupported_type", "The file is of no type a conversion reads.") from None
    except ArchiveTooLarge:
        raise Refusal(413, "archive_too_large", "The archive expands beyond what a document holds.") from None
    return detected, hashlib.sha256(data).digest()


def _title(given: str | None, file_name: str) -> str:
    if given is None or not given.strip():
        return PurePosixPath(file_name).stem[:MAX_TITLE_SIGNS]
    try:
        title = plain_text(given.strip())
    except ValueError:
        raise Refusal(422, "title_invalid", "The title holds control or invisible signs.") from None
    if len(title) > MAX_TITLE_SIGNS:
        raise Refusal(422, "title_too_long", f"The title is longer than {MAX_TITLE_SIGNS} signs.")
    return title
