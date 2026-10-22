"""Jobs as their owner follows them: the state, and a cancel.

A job's lane is the account that started it (``account_lane``). Another account gets the 404
of a job that does not exist, so ids reveal nothing; an admin, who runs the service, sees and
cancels every job. Who may see or cancel a job is decided in the query (``lane``), never in
Python after loading it.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.deps import require_account
from app.api.errors import AUTH_RESPONSES
from app.core.auth import Principal
from app.jobs.queue import account_lane, request_cancel
from app.jobs.state import JobState, job_state

router = APIRouter(prefix="/api/v1", tags=["jobs"], responses=AUTH_RESPONSES)
Account = Annotated[Principal, Depends(require_account)]


class Progress(BaseModel):
    code: str
    params: dict[str, Any]


class JobOut(BaseModel):
    id: UUID
    kind: str
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    progress: Progress | None
    error_code: str | None
    cancel_requested: bool
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@router.get("/jobs/{job_id}", summary="The state of a job")
async def get_job(job_id: UUID, request: Request, who: Account) -> JobOut:
    async with request.app.state.pool.connection() as connection:
        return _out(await _visible(connection, job_id, _lane(who)))


@router.post("/jobs/{job_id}/cancel", summary="Cancel a waiting job, or ask a running one to stop")
async def cancel_job(job_id: UUID, request: Request, who: Account) -> JobOut:
    """A waiting job ends at once; a running one stops at its worker's next heartbeat."""
    lane = _lane(who)
    async with request.app.state.pool.connection() as connection:
        await _visible(connection, job_id, lane)
        if not await request_cancel(connection, job_id, lane):
            raise HTTPException(409, "The job has ended.")
        state = await job_state(connection, job_id, lane)
    assert state is not None  # noqa: S101 - jobs are not deleted
    return _out(state)


def _lane(who: Principal) -> str | None:
    """The lane whose jobs ``who`` follows; ``None`` for an admin, who follows every lane."""
    if "admin" in who.roles:
        return None
    if who.account_id is None:  # require_account lets no visitor through; never every lane
        raise HTTPException(404, "No such job.")
    return account_lane(who.account_id)


async def _visible(connection: psycopg.AsyncConnection, job_id: UUID, lane: str | None) -> JobState:
    state = await job_state(connection, job_id, lane)
    if state is None:
        raise HTTPException(404, "No such job.")
    return state


def _out(state: JobState) -> JobOut:
    return JobOut.model_validate(state.__dict__)
