"""Documents and their extraction (plan M1 7.5, 7a): made of an entry's finished conversion, with
their extraction started at once; started again where it ended; read with their runs.

One extraction of a document waits or runs at a time (job.unique_key): a start while one does gives
that one back (200), as a conversion asked again does; the database holds to it beside a start
in another request. Only the document's owner starts its extraction - the owner is charged for it
(plan M1 5.6) and follows its job in their own lane; another who sees the document (editors) is
told 403, one who does not the 404 of no document. A start is admitted as a model job (budget,
jobs in flight, starts a minute) in the transaction that makes it, so a refusal takes the
document back too. Who may read a document reads its runs (app/db/documents.py, DOCUMENT_VISIBLE);
its job is followed and cancelled at /api/v1/jobs (app/api/jobs.py).
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.deps import require_account
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.jobs import JobOut, job_out
from app.api.limits import admit_model_start
from app.api.source_content import EDITORS
from app.core.auth import Principal
from app.core.logging import current_request_id
from app.db.accounts import record_audit
from app.db.documents import Document, DocumentError, create_document, documents_of, get_document
from app.db.runs import RunState, runs_of
from app.db.source_queries import Reader
from app.jobs.queue import JobStatus, OpenJob, account_lane, enqueue, last_jobs, open_job
from app.jobs.state import job_state
from app.pipeline.extraction import KIND, unique_key
from app.sources.register import EDUCATION_SECTORS
from app.vocab.lookup import notations_of

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]
Notation = Annotated[str, StringConstraints(min_length=1, max_length=40)]
MOST_LISTED = 100

START_REFUSALS: dict[int | str, dict[str, object]] = {
    403: {"model": ErrorBody, "description": "no_budget: no tokens left; not_owner: another's document"},
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
        **START_REFUSALS,
        404: {"model": ErrorBody, "description": "no_conversion: no finished conversion the caller may read"},
        422: {"model": ErrorBody, "description": "unknown_sector, unknown_region"},
    },
)
async def make_document(body: DocumentRequest, request: Request, who: Account) -> StartedOut:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    settings = request.app.state.settings
    async with request.app.state.pool.connection() as connection, connection.transaction():
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
        await admit_model_start(connection, who.account_id, settings)
        job_id = await _enqueue(connection, who.account_id, document.id)
        await record_audit(
            connection,
            who.account_id,
            who.name,
            "document.create",
            f"document:{document.id}",
            {"source": str(body.source_id), "conversion": str(body.conversion_id), "job": str(job_id)},
            current_request_id(),
        )
        [out] = await _outs(connection, [document], who)
        job = await _job(connection, job_id, who)
    return StartedOut(document=out, job=job)


@router.post(
    "/documents/{document_id}/extraction",
    summary="Start the document's extraction again, or follow the one waiting or running",
    status_code=202,
    responses={
        200: {"model": JobOut, "description": "The extraction waiting or running: no new one is made"},
        **START_REFUSALS,
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
                # looked for first: the one waiting or running is followed whatever the admission says
                if (open_id := await open_job(connection, unique_key(document.id))) is not None:
                    raise OpenJob(open_id)
                await admit_model_start(connection, who.account_id, request.app.state.settings)
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
    sectors = {iri: notation for notation, iri in (await notations_of(connection, EDUCATION_SECTORS)).items()}
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
