"""Starting the check of the register's candidates (plan M1, 2.5): an admin's, one at a time.

The check asks hosts of other people - some 140 for both seeds - each address once (the job
source.check, app/sources/check_job.py); two at once would ask twice, so a start while one waits
or runs is refused (409 check_running, naming the job to follow). The job is followed and
cancelled as any (``/api/v1/jobs/{id}``); an entry shows what the check found (``check``).
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import require_role
from app.api.errors import AUTH_RESPONSES, ErrorBody, Refusal
from app.core.auth import Principal
from app.core.logging import current_request_id
from app.db.accounts import record_audit
from app.jobs.queue import account_lane
from app.sources.check_job import enqueue_check
from app.sources.register import CheckOutcome, DetectedKind

router = APIRouter(prefix="/api/v1", tags=["sources"], responses=AUTH_RESPONSES)
Admin = Annotated[Principal, Depends(require_role("admin"))]


class CheckStarted(BaseModel):
    job_id: UUID


class CheckOut(BaseModel):
    """What the check found at the entry's address (url_check)."""

    outcome: CheckOutcome
    status_code: int | None
    detected_type: DetectedKind | None
    size: int | None
    checked_at: datetime


@router.post(
    "/sources/checks",
    status_code=202,
    summary="Check every candidate's address once (admins)",
    responses={409: {"model": ErrorBody, "description": "A check waits or runs already: details.job_id"}},
)
async def start_check(request: Request, admin: Admin) -> CheckStarted:
    """The check as a job of the admin's (``GET /api/v1/jobs/{id}``)."""
    assert admin.account_id is not None  # noqa: S101 - require_role refuses visitors
    async with request.app.state.pool.connection() as connection, connection.transaction():
        started, running = await enqueue_check(connection, account_lane(admin.account_id))
        if started is None:
            raise Refusal(
                409, "check_running", "A check waits or runs already.", details={"job_id": str(running)}
            )
        await record_audit(
            connection,
            admin.account_id,
            admin.name,
            "source.check",
            f"job:{started}",
            {},
            current_request_id(),
        )
    return CheckStarted(job_id=started)
