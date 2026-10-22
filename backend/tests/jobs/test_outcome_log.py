"""How a run's failure is said in the log (app/jobs/outcome.say_failure): once, with its cause."""

import asyncio
import logging
from uuid import uuid4

import pytest

from app.jobs.outcome import say_failure
from app.jobs.queue import Job, LeaseLost

JOB = Job(
    id=uuid4(),
    kind="source.fetch",
    lane="account:x",
    payload={},
    attempts=1,
    max_attempts=3,
    lease_owner="worker",
    lease_token=uuid4(),
    trace_id=None,
)


def test_a_cancel_the_handler_raised_itself_is_a_failure_with_its_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # no ending: the worker stopped nothing, the handler's own code raised it (a task inside it)
    cause = asyncio.CancelledError("an inner task was cancelled")

    with caplog.at_level(logging.WARNING, logger="app.jobs"):
        say_failure(JOB, cause, None)

    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].exc_info is not None and errors[0].exc_info[1] is cause


@pytest.mark.parametrize("ending", ["cancelled", "lost"])
def test_a_cancel_by_the_worker_is_how_the_run_was_stopped_not_a_failure(
    caplog: pytest.LogCaptureFixture, ending: str
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.jobs"):
        say_failure(JOB, asyncio.CancelledError(), ending)  # type: ignore[arg-type]

    assert caplog.records == []


def test_a_lease_lost_in_the_handler_is_no_failure_of_its_own(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.jobs"):
        say_failure(JOB, LeaseLost(), None)

    assert [record for record in caplog.records if record.levelno == logging.ERROR] == []
