"""Which handlers a worker runs: all it knows, or the kinds WORKER_KINDS names (conversions get
pods of their own, one job each)."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.jobs.handlers import select_handlers
from app.jobs.queue import Job
from tests.support import make_settings


async def anything(job: Job) -> Any:
    return None


KNOWN = {"source.fetch": anything, "source.convert": anything, "extract.run": anything}


def test_without_worker_kinds_a_worker_runs_every_kind() -> None:
    assert select_handlers(KNOWN, ()) == KNOWN


def test_worker_kinds_leave_the_others_to_other_workers() -> None:
    assert set(select_handlers(KNOWN, ("source.convert",))) == {"source.convert"}


def test_a_kind_no_handler_has_stops_the_start() -> None:
    # a typo would leave a pod idle that looks busy in the deployment
    with pytest.raises(ValueError, match=r"source\.convrt"):
        select_handlers(KNOWN, ("source.convrt",))


def test_the_settings_read_worker_kinds_as_a_comma_separated_list() -> None:
    assert make_settings(worker_kinds="source.fetch,source.convert").worker_kind_list == (
        "source.fetch",
        "source.convert",
    )
    assert make_settings().worker_kind_list == ()


@pytest.mark.parametrize("kinds", ["Source.fetch", "source.fetch, extract.run", "a,,b", ",", "source.fetch,"])
def test_worker_kinds_are_job_kinds_and_nothing_else(kinds: str) -> None:
    with pytest.raises(ValidationError, match="worker_kinds"):
        make_settings(worker_kinds=kinds)
