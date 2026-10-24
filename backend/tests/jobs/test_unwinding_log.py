"""How a handler left to unwind after its job ended is said in the log (app/jobs/worker.py,
_report_unwinding): meeting its lease is what it is meant to do, any other failure a warning."""

import asyncio
import logging
from uuid import uuid4

import pytest

from app.jobs import worker as workers
from app.jobs.queue import Job, LeaseLost

pytestmark = pytest.mark.anyio

JOB = Job(
    id=uuid4(),
    kind="extract.run",
    lane="account:x",
    payload={},
    attempts=1,
    max_attempts=3,
    lease_owner="worker",
    lease_token=uuid4(),
    trace_id=None,
)


async def ended_by(error: Exception) -> asyncio.Task[None]:
    async def handler() -> None:
        raise error

    task = asyncio.create_task(handler())
    await asyncio.wait({task})
    return task


async def test_a_handler_that_meets_its_lease_while_it_unwinds_is_no_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.jobs.worker"):
        workers._report_unwinding(JOB, await ended_by(LeaseLost(str(JOB.id))))
        workers._report_unwinding(JOB, await ended_by(ValueError("broken on its way out")))

    assert [(record.levelname, record.getMessage().split(":")[0]) for record in caplog.records] == [
        ("INFO", f"the handler of job {JOB.id} (extract.run) stopped at its lease"),
        ("WARNING", f"the handler of job {JOB.id} (extract.run) failed while it stopped"),
    ]
