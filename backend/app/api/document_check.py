"""A document checked again (plan M1 9; Paket 9 G9): POST /documents/{id}/check starts the job extract.check
- X5 again, no model asked (app/pipeline/x5_check.py) - by who may read the document, its owner and the
editors, once X5 has checked it (409 ``not_checked``: its extraction goes on). The job asks no model, so
neither the token budget nor the start limits of model jobs admit it. It shares the extraction's key:
beside a job of the document waiting or running it answers 200 with that one where the caller may follow
it - the one who started it, an admin -, else 409 ``job_open``.

simplify: who reads a document starts its check, as who edits it (app/db/editing.py).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import require_account
from app.api.document_access import visible_document
from app.api.edit_answers import audit
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.api.jobs import JobOut, job_out
from app.core.auth import Principal
from app.db.nodes import lock_tree
from app.db.runs import done_stages
from app.jobs.queue import OpenJob, account_lane, enqueue, open_job
from app.jobs.state import job_state
from app.pipeline.extraction import CHECK_KIND, unique_key

router = APIRouter(prefix="/api/v1", tags=["documents"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]


@router.post(
    "/documents/{document_id}/check",
    summary="Check the document again: X5, with no model",
    status_code=202,
    responses={
        200: {"model": JobOut, "description": "A job of the document waiting or running: none is made"},
        404: {"model": ErrorBody, "description": "no_document: none the caller may read"},
        409: {
            "model": ErrorBody,
            "description": "not_checked: X5 has not checked the document yet; job_open: another's job of"
            " the document waits or runs",
        },
    },
)
async def start_check(document_id: UUID, request: Request, response: Response, who: Account) -> JobOut:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    async with request.app.state.pool.connection() as connection:
        try:
            async with connection.transaction():
                document = await visible_document(connection, who, document_id)
                key = unique_key(document.id)
                await lock_tree(connection, document.id)  # as the extraction's start (app/api/documents.py)
                if (waiting := await open_job(connection, key)) is not None:
                    raise OpenJob(waiting)
                if "X5" not in await done_stages(connection, document.id):
                    raise Refusal(409, "not_checked", "X5 has not checked the document yet: extract it on.")
                payload = {"document_id": str(document.id)}
                job_id = await enqueue(
                    connection, CHECK_KIND, account_lane(who.account_id), payload, unique_key=key
                )
                await audit(connection, who, "check.start", f"document:{document.id}", {"job": str(job_id)})
        except OpenJob as open_one:  # rolled back
            response.status_code = 200
            job_id = open_one.job_id
        state = await job_state(
            connection, job_id, None if "admin" in who.roles else account_lane(who.account_id)
        )
    if state is None:  # another's job, whose id it is not the caller's to follow
        raise Refusal(409, "job_open", "A job of the document waits or runs: check it once that has ended.")
    return job_out(state)
