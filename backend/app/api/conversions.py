"""A register entry's conversion (X0): asked for, followed, read page by page (plan M1, 3.6).

The conversion belongs to the entry's file, which entries of several accounts may share by its
SHA-256; so it is reached through an entry, and who may ask for it and read it is who may read the
entry's file (app/api/source_content.py). Its job is named only to those who may follow it - the
account that started it, an admin (app/api/jobs.py); another sees the conversion's own state. That an
account's own upload comes with a conversion already done tells it that the same file was here
before: the price of converting a file once, whoever brings it.

Asking starts the job source.convert and answers 202, or gives back the conversion there - waiting,
running or done - with 200; a failed one is asked anew. Only a PDF is converted so far (Docling
and OCR follow in 3b).
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from app.api.deps import principal, require_account
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.limits import within_limit
from app.api.source_content import content_row
from app.conversion.base import Block, Cell, EngineName
from app.conversion.job import KIND
from app.core.auth import Principal
from app.core.ids import new_id
from app.core.logging import current_request_id
from app.db.accounts import record_audit
from app.db.conversions import (
    ConversionState,
    ConversionStatus,
    blocks_on_page,
    conversion_for,
    lock_conversion,
    start_conversion,
    tables_running_onto,
)
from app.jobs.queue import account_lane, enqueue

router = APIRouter(prefix="/api/v1", tags=["conversions"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Caller = Annotated[Principal, Depends(principal)]
PDF = "application/pdf"


class FindingOut(BaseModel):
    code: str
    params: dict[str, Any]


class ConversionOut(BaseModel):
    id: UUID
    engine: EngineName
    engine_version: str | None
    status: ConversionStatus
    # why it failed: unreadable, too_many_pages, needs_ocr, empty, timed_out, died, not_pdf, file_gone,
    # or the code of the job that ended without it (handler_error, cancelled, lease_lost)
    error_code: str | None
    # the job converting it, for those who may follow it (GET /api/v1/jobs/{id}); else null
    job_id: UUID | None
    pages: int | None
    printed_pages: list[str | None] | None
    findings: list[FindingOut]
    created_at: datetime
    finished_at: datetime | None


class ConversionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: EngineName = "pdfplumber"


class ContinuedOut(BaseModel):
    """A table begun on an earlier page and running on to this one: its block's ID, the page it
    begins on, and its cells on this page - a table joined over pages is one block, on its first."""

    id: str
    page: int
    cells: list[Cell]


class PageOut(BaseModel):
    page: int
    printed_page: str | None
    blocks: list[Block]
    continued: list[ContinuedOut]


CONTENT_REFUSALS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorBody, "description": "file_hidden: the entry's file is for its editors only"},
    404: {"model": ErrorBody, "description": "No such entry for the caller; no_file: it has no file yet"},
}


@router.post(
    "/sources/{source_id}/conversions",
    summary="Ask for the conversion of the entry's file into blocks",
    status_code=202,
    responses={
        200: {"model": ConversionOut, "description": "The conversion there: waiting, running or done"},
        **CONTENT_REFUSALS,
        422: {"model": ErrorBody, "description": "not_pdf: only a PDF is converted so far"},
        429: {"model": ErrorBody, "description": "too_many_conversions: started too many this minute"},
    },
)
async def ask_conversion(
    source_id: UUID,
    request: Request,
    response: Response,
    who: Account,
    body: Annotated[ConversionRequest | None, Body()] = None,
) -> ConversionOut:
    engine = (body or ConversionRequest()).engine
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    async with request.app.state.pool.connection() as connection, connection.transaction():
        row = await content_row(connection, who, request.app.state.settings, source_id)
        file_id = _file_of(row)
        if row["mime"] != PDF:
            raise Refusal(422, "not_pdf", "Only a PDF is converted so far.")
        await lock_conversion(connection, file_id, engine)
        there = await conversion_for(connection, file_id, engine)
        if there is not None and there.status != "failed":
            response.status_code = 200
            return _out(there, who)
        settings = request.app.state.settings
        await within_limit(
            connection, who.account_id, KIND, settings.conversions_per_minute, "too_many_conversions"
        )
        conversion_id = there.id if there else new_id()
        job_id = await enqueue(
            connection, KIND, account_lane(who.account_id), {"conversion_id": str(conversion_id)}
        )
        await start_conversion(
            connection,
            conversion_id,
            source_file_id=file_id,
            engine=engine,
            account_id=who.account_id,
            job_id=job_id,
        )
        await record_audit(
            connection,
            who.account_id,
            who.name,
            "source.convert",
            f"source:{source_id}",
            {"conversion": str(conversion_id), "job": str(job_id), "engine": engine},
            current_request_id(),
        )
        started = await conversion_for(connection, file_id, engine)
    assert started is not None  # noqa: S101 - started in this transaction
    return _out(started, who)


@router.get(
    "/sources/{source_id}/conversion",
    summary="The conversion of the entry's file: how far it is, its pages and findings",
    responses={
        403: CONTENT_REFUSALS[403],
        404: {
            "model": ErrorBody,
            "description": "No such entry for the caller; no_file: it has no file yet; no_conversion: none"
            " was asked for",
        },
    },
)
async def get_conversion(
    source_id: UUID, request: Request, who: Caller, engine: EngineName = "pdfplumber"
) -> ConversionOut:
    async with request.app.state.pool.connection() as connection:
        state = await _conversion(connection, who, request, source_id, engine)
    return _out(state, who)


@router.get(
    "/sources/{source_id}/conversion/blocks",
    summary="The blocks of one page of the converted file, in reading order",
    responses={
        403: CONTENT_REFUSALS[403],
        404: {
            "model": ErrorBody,
            "description": "No such entry for the caller; no_file; no_conversion; no_such_page: the file"
            " has fewer pages",
        },
        409: {"model": ErrorBody, "description": "not_converted: the conversion is not done"},
    },
)
async def get_blocks(
    source_id: UUID,
    request: Request,
    who: Caller,
    page: Annotated[int, Query(ge=1, le=100_000)],
    engine: EngineName = "pdfplumber",
) -> PageOut:
    async with request.app.state.pool.connection() as connection:
        state = await _conversion(connection, who, request, source_id, engine)
        if state.status != "done" or state.pages is None or state.printed_pages is None:
            raise Refusal(409, "not_converted", "The conversion is not done.")
        if page > state.pages:
            raise Refusal(404, "no_such_page", f"The file has {state.pages} pages.")
        blocks = await blocks_on_page(connection, state.id, page)
        running = await tables_running_onto(connection, state.id, page)
    continued = [
        ContinuedOut(id=table.block_id, page=table.page, cells=list(table.cells)) for table in running
    ]
    return PageOut(page=page, printed_page=state.printed_pages[page - 1], blocks=blocks, continued=continued)


async def _conversion(
    connection: Any, who: Principal, request: Request, source_id: UUID, engine: str
) -> ConversionState:
    row = await content_row(connection, who, request.app.state.settings, source_id)
    state = await conversion_for(connection, _file_of(row), engine)
    if state is None:
        raise Refusal(404, "no_conversion", "The entry's file has not been converted.")
    return state


def _file_of(row: dict[str, Any]) -> UUID:
    if row["file_id"] is None:
        raise Refusal(404, "no_file", "The entry has no file yet.")
    file_id: UUID = row["file_id"]
    return file_id


def _out(state: ConversionState, who: Principal) -> ConversionOut:
    follows = "admin" in who.roles or (
        who.account_id is not None and state.job_lane == account_lane(who.account_id)
    )
    return ConversionOut(
        id=state.id,
        engine=state.engine,  # the table's CHECK holds it to EngineName; pydantic checks it again
        engine_version=state.engine_version,
        status=state.status,
        error_code=state.error_code,
        job_id=state.job_id if follows else None,
        pages=state.pages,
        printed_pages=state.printed_pages,
        findings=[FindingOut(**finding) for finding in state.findings],
        created_at=state.created_at,
        finished_at=state.finished_at,
    )
