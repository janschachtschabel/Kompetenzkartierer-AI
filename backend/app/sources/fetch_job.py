"""The job source.fetch: a register entry's URL fetched, its file stored, the entry acquired.

A server that refuses (4xx) or asks to slow down (429), an address inside the network, a file too
large, a redirect loop, an answer no attempt can use or a file of no type a conversion reads end
the job (PermanentError, with a code the interface words); a server away for a moment, a broken
transfer or a timeout are tried again by the queue. The entry's register status says what was
found: unreachable, reachable (it answered, its file is of no use here), or acquired. The file is
named by the last address of the chain, or by the first.
"""

import asyncio
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

import httpx2

from app.core.auth import visible_only
from app.db.sources import StoredFile, fetch_target, record_fetch, set_register_status
from app.jobs.context import JobContext
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job
from app.sources.archives import ArchiveTooLarge, ArchiveUnreadable
from app.sources.filetype import MAX_NAME_SIGNS, UnsupportedType, examine, stored_name
from app.sources.url_fetch import (
    BadAnswer,
    DownloadError,
    Fetched,
    FileTooLarge,
    TooManyRedirects,
    UrlNotAllowed,
    fetch,
    filename_from_url,
)

KIND = "source.fetch"
MIB = 2**20
MAX_TITLE_SIGNS = 500


async def fetch_source(
    context: JobContext, job: Job, *, transport: httpx2.AsyncBaseTransport | None = None
) -> dict[str, Any]:
    """Fetch the entry ``job.payload["source_id"]`` names; ``transport`` is the network (tests)."""
    source_id = UUID(str(job.payload["source_id"]))
    async with context.pool.connection() as connection:
        target = await fetch_target(connection, source_id)
    if target is None or target.url is None:
        raise PermanentError("source_missing", "The register entry has no address to fetch.")
    if target.stored is not None:  # a run again after the entry got its file: nothing to fetch
        return _result(source_id, target.stored)
    fetched = await _fetched(
        context, source_id, target.url, transport, last_attempt=job.attempts >= job.max_attempts
    )
    name = filename_from_url(fetched.chain[-1]) or filename_from_url(target.url) or ""
    try:
        detected, digest = await asyncio.to_thread(examine, name, fetched.content)
    except (UnsupportedType, ArchiveUnreadable):
        await _note(context, source_id, "reachable")
        raise PermanentError("unsupported_type", "The file is of no type a conversion reads.") from None
    except ArchiveTooLarge:
        await _note(context, source_id, "reachable")
        raise PermanentError(
            "archive_too_large", "The archive expands beyond what a document holds."
        ) from None
    file_name = stored_name(name, detected)
    stored = StoredFile(
        sha256=digest, size=len(fetched.content), mime=detected.mime, storage_key=f"sources/{digest.hex()}"
    )
    if not await context.storage.exists(stored.storage_key):
        await context.storage.put(stored.storage_key, fetched.content)
    async with context.pool.connection() as connection:
        await record_fetch(
            connection,
            source_id=source_id,
            account_id=target.owner_id,
            stored=stored,
            file_name=file_name,
            received_name=visible_only(name)[:MAX_NAME_SIGNS],
            chain=fetched.chain,
            # the stem trimmed, as an upload's ("Lehrplan .pdf"); should nothing be left, the name
            title=PurePosixPath(file_name).stem[:MAX_TITLE_SIGNS].strip() or file_name[:MAX_TITLE_SIGNS],
        )
    return _result(source_id, stored)


def _result(source_id: UUID, stored: StoredFile) -> dict[str, Any]:
    return {"source_id": str(source_id), "sha256": stored.sha256.hex(), "size": stored.size}


async def _fetched(
    context: JobContext,
    source_id: UUID,
    url: str,
    transport: httpx2.AsyncBaseTransport | None,
    *,
    last_attempt: bool,
) -> Fetched:
    """The file at ``url``, or PermanentError for a failure another attempt would meet again,
    the entry's status noting what was found; any other DownloadError is tried again, and at the
    ``last_attempt`` leaves the entry unreachable."""
    try:
        return await fetch(
            url,
            max_bytes=context.settings.max_upload_mb * MIB,
            transport=transport,
            user_agent=context.settings.fetch_user_agent,
        )
    except UrlNotAllowed as error:
        await _note(context, source_id, "unreachable")
        raise PermanentError("url_not_allowed", str(error)) from None
    except FileTooLarge as error:
        await _note(context, source_id, "reachable")
        raise PermanentError("file_too_large", str(error)) from None
    except TooManyRedirects as error:
        await _note(context, source_id, "reachable")
        raise PermanentError("too_many_redirects", str(error)) from None
    except BadAnswer as error:
        await _note(context, source_id, "reachable")
        raise PermanentError("bad_answer", str(error)) from None
    except DownloadError as error:
        if error.status == 429:  # another attempt within seconds would only press the server
            await _note(context, source_id, "reachable")
            raise PermanentError("download_throttled", str(error)) from None
        if error.status is not None and 400 <= error.status < 500:
            await _note(context, source_id, "unreachable")
            raise PermanentError("download_refused", str(error)) from None
        if last_attempt:  # the queue fails the job: the entry must not stay unchecked
            await _note(context, source_id, "unreachable")
        raise  # away for a moment: another attempt


async def _note(context: JobContext, source_id: UUID, status: str) -> None:
    async with context.pool.connection() as connection:
        await set_register_status(connection, source_id, status)
