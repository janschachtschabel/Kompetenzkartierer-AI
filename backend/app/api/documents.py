"""Documents and their extraction (plan M1 7.5, 7a): made of an entry's finished conversion, with
their extraction started at once; started again where it ended; read with their runs.

One extraction of a document waits or runs at a time (job.unique_key): a start while one does gives
that one back (200), as a conversion asked again does; the database holds to it beside a start
in another request. So does an account's document asked of an entry's conversion one of its
documents of that entry is being extracted from: the form sent twice, a request sent again, is
led to that document (200, ``made`` false); once that extraction has ended another document of it
may be made (another sector, other Länder). A deliberate start of another of its documents is no
second sending, and goes. Both are looked for once the admission's lock is held, and also where it
refuses: what started beside the request is followed whatever the admission says. Only the
document's owner starts its extraction - the owner is charged for it (plan M1 5.6) and follows its
job in their own lane - and only while the entry's content is still theirs to read (403
``file_hidden``); following the one waiting or running reads none. Another who sees the document
(editors) is told 403, one who does not the 404 of no document. A start is admitted as a model job (budget,
jobs in flight, starts a minute) in the transaction that makes it, so a refusal takes the
document back too. Who may read a document reads its runs (app/db/documents.py, DOCUMENT_VISIBLE);
its job is followed and cancelled at /api/v1/jobs (app/api/jobs.py).
"""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.deps import require_account
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.jobs import JobOut, job_out
from app.api.limits import admit_model_start
from app.api.source_content import EDITORS, content_row
from app.core.auth import Principal
from app.core.logging import current_request_id
from app.core.settings import Settings
from app.db.accounts import record_audit
from app.db.documents import (
    Document,
    DocumentError,
    create_document,
    documents_made_of,
    documents_of,
    get_document,
)
from app.db.runs import RunState, runs_of
from app.db.source_queries import Reader
from app.jobs.queue import JobStatus, OpenJob, account_lane, enqueue, last_jobs, open_job, open_jobs
from app.jobs.state import job_state
from app.pipeline.extraction import KIND, unique_key
from app.vocab.lookup import notations_by_iri

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Notation = Annotated[str, StringConstraints(min_length=1, max_length=40)]
MOST_LISTED = 100

START_REFUSALS: dict[int | str, dict[str, object]] = {
    403: {"model": ErrorBody, "description": "no_budget: no tokens left"},
    429: {"model": ErrorBody, "description": "too_many_jobs, too_many_starts: wait and try again"},
}


class DocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    conversion_id: UUID
    sector: Notation  # a notation of cv:EducationSectors, "school"
    regions: list[Notation] = Field(default_factory=list, max_length=17)  # "DE-NW"; "DE" for all


class ExtractionRef(BaseModel):
    # the job, for those who may follow it (GET /api/v1/jobs/{id}): its owner, an admin; else null
    job_id: UUID | None
    status: JobStatus


class DocumentOut(BaseModel):
    id: UUID
    source_id: UUID
    conversion_id: UUID
    own: bool  # the caller's: who may start its extraction
    title: str | None
    document_type_iri: str | None
    sector: str  # the notation, "school"
    regions: list[str]
    created_at: datetime
    extraction: ExtractionRef | None  # the latest extraction job, whatever became of it


class StartedOut(BaseModel):
    document: DocumentOut
    job: JobOut
    # false where the account's document of the entry being extracted came back instead (200)
    made: bool


class RunOut(BaseModel):
    stage: str
    attempt: int | None
    state: RunState
    started_at: datetime
    finished_at: datetime | None
    failure: str | None


@router.post(
    "/documents",
    summary="Make a document of an entry's finished conversion and start its extraction",
    status_code=202,
    responses={
        200: {
            "model": StartedOut,
            "description": "The caller's document of it being extracted: none is made",
        },
        **START_REFUSALS,
        404: {"model": ErrorBody, "description": "no_conversion: no finished conversion the caller may read"},
        422: {"model": ErrorBody, "description": "unknown_sector, unknown_region"},
    },
)
async def make_document(
    body: DocumentRequest, request: Request, response: Response, who: Account
) -> StartedOut:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    owner, settings = who.account_id, request.app.state.settings
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                try:
                    document = await create_document(
                        connection,
                        _reader(who),
                        third_party_content=settings.third_party_markdown != "hidden",
                        source_id=body.source_id,
                        conversion_id=body.conversion_id,
                        sector=body.sector,
                        regions=body.regions,
                    )
                except DocumentError as refused:
                    raise _refusal(refused) from None
                await _admit(
                    connection,
                    owner,
                    settings,
                    lambda: _being_extracted(connection, owner, body.source_id, body.conversion_id),
                )
                job_id = await _enqueue(connection, owner, document.id)
                await record_audit(
                    connection,
                    owner,
                    who.name,
                    "document.create",
                    f"document:{document.id}",
                    {
                        "source": str(body.source_id),
                        "conversion": str(body.conversion_id),
                        "job": str(job_id),
                    },
                    current_request_id(),
                )
        except _BeingExtracted as found:  # rolled back, the document asked and its admission with it
            response.status_code = 200
            document, job_id = found.document, found.job_id
        [out] = await _outs(connection, [document], who)
        made = response.status_code != 200
        return StartedOut(document=out, job=await _job(connection, job_id, who), made=made)


@router.post(
    "/documents/{document_id}/extraction",
    summary="Start the document's extraction again, or follow the one waiting or running",
    status_code=202,
    responses={
        200: {"model": JobOut, "description": "The extraction waiting or running: no new one is made"},
        **START_REFUSALS,
        403: {
            "model": ErrorBody,
            "description": "no_budget: no tokens left; not_owner: another's document; "
            "file_hidden: the entry's content is no longer the owner's to read",
        },
        404: {"model": ErrorBody, "description": "no_document: none the caller may read"},
    },
)
async def start_extraction(document_id: UUID, request: Request, response: Response, who: Account) -> JobOut:
    """A new extraction job goes on where the last one stopped (plan M1 6.6: the stages done on the
    document are passed over)."""
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                document = await _visible(connection, who, document_id)
                if document.owner_id != who.account_id:
                    raise Refusal(403, "not_owner", "Only the document's owner starts its extraction.")
                settings = request.app.state.settings
                key = unique_key(document.id)
                await _open(connection, key)  # following the one waiting or running reads no content
                await _readable(connection, who, settings, document)
                await _admit(connection, who.account_id, settings, lambda: _open(connection, key))
                job_id = await _enqueue(connection, who.account_id, document.id)
                await record_audit(
                    connection,
                    who.account_id,
                    who.name,
                    "extraction.start",
                    f"document:{document.id}",
                    {"job": str(job_id)},
                    current_request_id(),
                )
        except OpenJob as open_one:  # rolled back, the admission with it
            response.status_code = 200
            job_id = open_one.job_id
        return await _job(connection, job_id, who)


@router.get("/documents", summary="The documents the caller may read, the newest first")
async def list_documents(
    request: Request,
    who: Account,
    source_id: Annotated[UUID | None, Query(description="Those of this register entry only")] = None,
) -> list[DocumentOut]:
    async with request.app.state.pool.connection() as connection:
        found = await documents_of(connection, _reader(who), source_id=source_id, limit=MOST_LISTED)
        return await _outs(connection, found, who)


@router.get(
    "/documents/{document_id}",
    summary="A document",
    responses={404: {"model": ErrorBody, "description": "no_document: none the caller may read"}},
)
async def read_document(document_id: UUID, request: Request, who: Account) -> DocumentOut:
    async with request.app.state.pool.connection() as connection:
        [out] = await _outs(connection, [await _visible(connection, who, document_id)], who)
        return out


@router.get(
    "/documents/{document_id}/runs",
    summary="The runs of the document's extraction stages, in the order they began",
    responses={404: {"model": ErrorBody, "description": "no_document: none the caller may read"}},
)
async def read_runs(document_id: UUID, request: Request, who: Account) -> list[RunOut]:
    async with request.app.state.pool.connection() as connection:
        await _visible(connection, who, document_id)
        return [RunOut.model_validate(run.__dict__) for run in await runs_of(connection, document_id)]


def _reader(who: Principal) -> Reader:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    return Reader(account_id=who.account_id, sees_all=bool(who.roles & EDITORS))


def _refusal(refused: DocumentError) -> Refusal:
    if refused.code == "unknown_sector":
        return Refusal(422, "unknown_sector", "No such education sector.")
    if refused.code == "unknown_region":
        return Refusal(422, "unknown_region", "No such region.")
    return Refusal(404, "no_conversion", "No finished conversion of this entry the account may read.")


async def _visible(connection: psycopg.AsyncConnection, who: Principal, document_id: UUID) -> Document:
    document = await get_document(connection, _reader(who), document_id)
    if document is None:
        raise Refusal(404, "no_document", "No such document.")
    return document


class _BeingExtracted(Exception):
    """The caller's document of the conversion asked whose extraction waits or runs."""

    def __init__(self, document: Document, job_id: UUID) -> None:
        super().__init__(f"document {document.id} is being extracted")
        self.document = document
        self.job_id = job_id


async def _admit(
    connection: psycopg.AsyncConnection,
    account_id: UUID,
    settings: Settings,
    look: Callable[[], Awaitable[None]],
) -> None:
    """Admit the start as a model job, then ``look`` for an extraction it would stand beside -
    under the admission's lock, so one started in another request is seen; where the admission
    refuses too, so following one waiting or running asks for nothing (``look`` raises)."""
    try:
        await admit_model_start(connection, account_id, settings)
    except Refusal:
        await look()
        raise
    await look()


async def _open(connection: psycopg.AsyncConnection, key: str) -> None:
    if (open_id := await open_job(connection, key)) is not None:
        raise OpenJob(open_id)


async def _being_extracted(
    connection: psycopg.AsyncConnection, owner: UUID, source_id: UUID, conversion_id: UUID
) -> None:
    made = await documents_made_of(connection, owner, source_id, conversion_id)
    found = await open_jobs(connection, [unique_key(document.id) for document in made])
    for document in made:
        if (job_id := found.get(unique_key(document.id))) is not None:
            raise _BeingExtracted(document, job_id)


async def _readable(
    connection: psycopg.AsyncConnection, who: Principal, settings: Settings, document: Document
) -> None:
    """The entry's content still the owner's to read, as when the document was made - its own,
    every entry while an editor, one of no account while THIRD_PARTY_MARKDOWN opens it."""
    try:
        await content_row(connection, who, settings, document.source_id)
    except HTTPException as hidden:  # an entry no longer the owner's to see at all: hidden as well
        if hidden.status_code != 404:
            raise
        raise Refusal(403, "file_hidden", "The content of this entry is no longer yours to read.") from None


async def _enqueue(connection: psycopg.AsyncConnection, owner: UUID, document_id: UUID) -> UUID:
    return await enqueue(
        connection,
        KIND,
        account_lane(owner),
        {"document_id": str(document_id)},
        unique_key=unique_key(document_id),
    )


async def _job(connection: psycopg.AsyncConnection, job_id: UUID, who: Principal) -> JobOut:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    lane = None if "admin" in who.roles else account_lane(who.account_id)
    state = await job_state(connection, job_id, lane)
    assert state is not None  # noqa: S101 - the owner's own job, just made or found
    return job_out(state)


async def _outs(
    connection: psycopg.AsyncConnection, documents: list[Document], who: Principal
) -> list[DocumentOut]:
    """The documents as the API gives them, in two queries however many they are."""
    sectors = await notations_by_iri(connection, {document.sector_iri for document in documents})
    found = await last_jobs(connection, [unique_key(document.id) for document in documents])

    def extraction(document: Document) -> ExtractionRef | None:
        if (latest := found.get(unique_key(document.id))) is None:
            return None
        job_id, status = latest
        follows = "admin" in who.roles or document.owner_id == who.account_id
        return ExtractionRef(job_id=job_id if follows else None, status=status)

    return [
        DocumentOut(
            id=document.id,
            source_id=document.source_id,
            conversion_id=document.conversion_id,
            own=document.owner_id == who.account_id,
            title=document.title,
            document_type_iri=document.document_type_iri,
            sector=sectors.get(document.sector_iri, document.sector_iri),
            regions=list(document.regions),
            created_at=document.created_at,
            extraction=extraction(document),
        )
        for document in documents
    ]
