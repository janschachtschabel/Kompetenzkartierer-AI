"""A job carries the trace of the request that made it, and reports its progress under its lease.

The worker writes the job's lines with that trace id, so a request's lines and those of the
jobs it started are found together; between jobs its lines carry none.
"""

import io
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from app.core.logging import configure_logging
from app.core.tracing import take_trace_headers
from app.db.migrate import migrate
from app.jobs.queue import Job, LeaseLost, claim, enqueue, fail, report_progress
from app.jobs.worker import Worker

pytestmark = [pytest.mark.pg, pytest.mark.anyio, pytest.mark.usefixtures("restore_logging")]

TRACE = "trace-of-the-upload"


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as opened:
        yield opened


async def column(pool: AsyncConnectionPool, job_id: UUID, name: str) -> Any:
    async with pool.connection() as connection:
        cursor = await connection.execute(f"SELECT {name} FROM job WHERE id = %s", (job_id,))  # noqa: S608
        found = await cursor.fetchone()
    assert found is not None
    return found[0]


async def enqueue_traced(pool: AsyncConnectionPool, kind: str = "test.work") -> UUID:
    # as the API does it: the request's headers set the trace, the endpoint enqueues
    take_trace_headers([(b"x-client-trace-id", TRACE.encode())], "request-1")
    async with pool.connection() as connection:
        return await enqueue(connection, kind, "account-a")


async def test_a_job_keeps_the_trace_of_the_request_that_made_it(pool: AsyncConnectionPool) -> None:
    job_id = await enqueue_traced(pool)

    async with pool.connection() as connection:
        job = await claim(connection, "w1", ["test.work"], 60)

    assert job is not None and job.id == job_id
    assert job.trace_id == TRACE
    assert await column(pool, job_id, "trace_id") == TRACE


async def test_a_job_from_a_request_without_trace_headers_keeps_its_request_id(
    pool: AsyncConnectionPool,
) -> None:
    # the SPA and nginx send none: the request id still joins the request's lines and the job's
    take_trace_headers([], "request-from-the-page")
    async with pool.connection() as connection:
        job_id = await enqueue(connection, "test.work", "account-a")

    assert await column(pool, job_id, "trace_id") == "request-from-the-page"


@pytest.mark.parametrize("request_id", ["a b", "a" * 257], ids=["sign", "length"])
async def test_a_request_id_the_column_would_refuse_leaves_the_trace_empty(
    pool: AsyncConnectionPool, request_id: str
) -> None:
    # set_request_id never makes one; the job is still made, without a trace
    take_trace_headers([], request_id)
    async with pool.connection() as connection:
        job_id = await enqueue(connection, "test.work", "account-a")

    assert await column(pool, job_id, "trace_id") is None


async def test_a_job_made_outside_a_request_has_no_trace(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as connection:
        job_id = await enqueue(connection, "test.work", "system")

    assert await column(pool, job_id, "trace_id") is None


@pytest.mark.parametrize(("trace", "kept"), [("a" * 256, True), ("a" * 257, False), ("a b", False)])
async def test_the_table_keeps_a_trace_id_as_the_tracing_lets_one_through(
    pool: AsyncConnectionPool, trace: str, kept: bool
) -> None:
    take_trace_headers([], "request-2")
    async with pool.connection() as connection:
        job_id = await enqueue(connection, "test.work", "account-a")
        update = connection.execute("UPDATE job SET trace_id = %s WHERE id = %s", (trace, job_id))
        if kept:
            await update
        else:
            with pytest.raises(psycopg.errors.CheckViolation):
                await update


async def test_progress_is_written_under_the_job_s_lease(pool: AsyncConnectionPool) -> None:
    await enqueue_traced(pool)
    async with pool.connection() as connection:
        job = await claim(connection, "w1", ["test.work"], 60)
        assert job is not None

        await report_progress(connection, job, "converting", {"page": 3, "pages": 40})

    progress = await column(pool, job.id, "progress")
    assert progress == {"code": "converting", "params": {"page": 3, "pages": 40}}


async def test_a_worker_without_the_lease_writes_no_progress(pool: AsyncConnectionPool) -> None:
    await enqueue_traced(pool)
    async with pool.connection() as connection:
        job = await claim(connection, "w1", ["test.work"], 60)
        assert job is not None
        await report_progress(connection, job, "started", {})
        # another worker has it now: its claim got a new token
        await connection.execute("UPDATE job SET lease_token = gen_random_uuid() WHERE id = %s", (job.id,))

        with pytest.raises(LeaseLost):
            await report_progress(connection, job, "converting", {"page": 1})

    assert await column(pool, job.id, "progress") == {"code": "started", "params": {}}


async def test_a_new_attempt_starts_without_the_progress_of_the_last(pool: AsyncConnectionPool) -> None:
    # page 39 of 40 from a failed attempt is not where the next one stands
    await enqueue_traced(pool)
    async with pool.connection() as connection:
        job = await claim(connection, "w1", ["test.work"], 60)
        assert job is not None
        await report_progress(connection, job, "converting", {"page": 39, "pages": 40})
        assert await fail(connection, job, "converter_down", "no answer", retry=True) == "queued"
        await connection.execute("UPDATE job SET run_after = now() WHERE id = %s", (job.id,))

        again = await claim(connection, "w2", ["test.work"], 60)

    assert again is not None and again.id == job.id
    assert await column(pool, job.id, "progress") is None


async def test_the_worker_writes_the_job_s_lines_with_its_trace(pool: AsyncConnectionPool) -> None:
    stream = io.StringIO()
    configure_logging("INFO", "json", stream=stream)
    job_id = await enqueue_traced(pool)
    take_trace_headers([], "worker")  # the worker runs outside any request

    async def work(job: Job) -> None:
        logging.getLogger("app.test").info("inside the job")

    await Worker(pool, {"test.work": work}, owner="w1").run_once()
    logging.getLogger("app.test").info("after the job")

    lines = {line["message"]: line for line in map(json.loads, stream.getvalue().splitlines())}
    assert lines["inside the job"]["trace_id"] == TRACE
    assert lines["after the job"]["trace_id"] == "-"
    assert await column(pool, job_id, "status") == "done"
