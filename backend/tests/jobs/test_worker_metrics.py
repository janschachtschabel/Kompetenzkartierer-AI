"""The worker counts its jobs by kind and ending, times them, and answers /health and /metrics
on its internal port: the cluster's liveness probe and Prometheus ask there."""

import asyncio
import logging
import socket
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx2
import pytest
from prometheus_client import REGISTRY
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import migrate
from app.jobs.probes import probe_server
from app.jobs.queue import Job, enqueue, report_progress, request_cancel
from app.jobs.worker import Handler, PermanentError, Result, Worker

pytestmark = pytest.mark.anyio


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
async def pool(database_url: str) -> AsyncIterator[AsyncConnectionPool]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as opened:
        yield opened


async def ends_done(job: Job) -> dict[str, Any]:
    return {}


async def ends_failed(job: Job) -> None:
    raise PermanentError("bad_input", "the file is no PDF")


async def ends_in_error(job: Job) -> None:
    raise RuntimeError("invented")


@pytest.mark.pg
@pytest.mark.parametrize(
    ("handler", "outcome"),
    [(ends_done, "done"), (ends_failed, "failed"), (ends_in_error, "error")],
    ids=["done", "failed", "error"],
)
async def test_a_job_is_counted_by_its_kind_and_how_it_ended(
    pool: AsyncConnectionPool, handler: Handler, outcome: str
) -> None:
    kind = f"test.metrics_{outcome}"
    async with pool.connection() as connection:
        await enqueue(connection, kind, "account-a")
    counted = sample("kka_jobs_total", kind=kind, outcome=outcome)
    timed = sample("kka_job_duration_seconds_count", kind=kind)

    await Worker(pool, {kind: handler}, owner="w1").run_once()

    assert sample("kka_jobs_total", kind=kind, outcome=outcome) == counted + 1
    assert sample("kka_job_duration_seconds_count", kind=kind) == timed + 1


@pytest.mark.pg
@pytest.mark.parametrize("ending", ["cancelled", "lost"])
async def test_a_cancel_and_a_lost_lease_are_counted_too(pool: AsyncConnectionPool, ending: str) -> None:
    kind = f"test.metrics_{ending}"
    async with pool.connection() as connection:
        job_id = await enqueue(connection, kind, "account-a")
    started = asyncio.Event()

    async def waits(job: Job) -> None:
        started.set()
        await asyncio.sleep(30)

    async def interrupt() -> None:
        await started.wait()
        async with pool.connection() as connection:
            if ending == "cancelled":
                await request_cancel(connection, job_id, "account-a")
            else:  # another worker's claim now
                steal = "UPDATE job SET lease_token = gen_random_uuid() WHERE id = %s"
                await connection.execute(steal, (job_id,))

    counted = sample("kka_jobs_total", kind=kind, outcome=ending)
    # a lease of 3 s is renewed every second: the worker learns of the cancel or the loss then
    await asyncio.gather(Worker(pool, {kind: waits}, owner="w1", lease_s=3).run_once(), interrupt())

    assert sample("kka_jobs_total", kind=kind, outcome=ending) == counted + 1


async def steal(pool: AsyncConnectionPool, job: Job) -> None:
    """Another worker's claim now, as after a sweep that found the lease expired."""
    async with pool.connection() as connection:
        await connection.execute("UPDATE job SET lease_token = gen_random_uuid() WHERE id = %s", (job.id,))


async def job_row(pool: AsyncConnectionPool, job_id: UUID) -> tuple[Any, ...]:
    async with pool.connection() as connection:
        cursor = await connection.execute("SELECT status, result, error FROM job WHERE id = %s", (job_id,))
        found = await cursor.fetchone()
    assert found is not None
    return tuple(found)


def errors_of(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]


@pytest.mark.pg
async def test_a_lease_the_handler_learns_is_lost_counts_as_lost(
    pool: AsyncConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    # the handler's progress report is the first to see it: the job is another worker's
    kind = "test.metrics_progress_lost"
    async with pool.connection() as connection:
        job_id = await enqueue(connection, kind, "account-a")

    async def reports(job: Job) -> dict[str, Any]:
        await steal(pool, job)
        async with pool.connection() as connection:
            await report_progress(connection, job, "converting", {"page": 1})
        return {}

    before = {outcome: sample("kka_jobs_total", kind=kind, outcome=outcome) for outcome in ("lost", "error")}
    timed = sample("kka_job_duration_seconds_count", kind=kind)
    caplog.set_level(logging.WARNING, logger="app.jobs.worker")

    await Worker(pool, {kind: reports}, owner="w1").run_once()

    assert sample("kka_jobs_total", kind=kind, outcome="lost") == before["lost"] + 1
    assert sample("kka_jobs_total", kind=kind, outcome="error") == before["error"]
    assert sample("kka_job_duration_seconds_count", kind=kind) == timed + 1
    assert errors_of(caplog) == []
    assert await job_row(pool, job_id) == ("running", None, None)  # as the other worker has it


async def returns_a_result(job: Job) -> dict[str, Any]:
    return {"value": 1}


async def fails(job: Job) -> None:
    raise RuntimeError("invented")


@pytest.mark.pg
@pytest.mark.parametrize(
    ("ends", "outcome"), [(returns_a_result, "done"), (fails, "error")], ids=["done", "error"]
)
async def test_a_lease_lost_between_two_heartbeats_counts_as_lost_at_the_end(
    pool: AsyncConnectionPool, caplog: pytest.LogCaptureFixture, ends: Handler, outcome: str
) -> None:
    # the lease expired while the loop was held, a sweep handed the job on; no heartbeat saw it
    kind = f"test.metrics_end_lost_{outcome}"
    async with pool.connection() as connection:
        job_id = await enqueue(connection, kind, "account-a")

    async def handler(job: Job) -> Result:
        await steal(pool, job)
        return await ends(job)

    before = {name: sample("kka_jobs_total", kind=kind, outcome=name) for name in ("lost", outcome)}
    timed = sample("kka_job_duration_seconds_count", kind=kind)
    caplog.set_level(logging.WARNING, logger="app.jobs.worker")

    await Worker(pool, {kind: handler}, owner="w1").run_once()

    assert sample("kka_jobs_total", kind=kind, outcome="lost") == before["lost"] + 1
    assert sample("kka_jobs_total", kind=kind, outcome=outcome) == before[outcome]
    assert sample("kka_job_duration_seconds_count", kind=kind) == timed + 1
    assert errors_of(caplog) == []
    assert await job_row(pool, job_id) == ("running", None, None)


@pytest.mark.pg
async def test_a_sweep_counts_the_expired_leases_by_what_became_of_their_jobs(
    pool: AsyncConnectionPool,
) -> None:
    # a worker that died, or a loop held past its lease: no run of this worker ends, the sweep
    # is the only one to see it
    ends = {"queued": (1, False), "failed": (3, False), "cancelled": (1, True)}
    async with pool.connection() as connection:
        for attempts, cancel in ends.values():
            job_id = await enqueue(connection, "test.metrics_expired", "account-a", max_attempts=3)
            await connection.execute(
                "UPDATE job SET status = 'running', lease_owner = 'gone', lease_token = gen_random_uuid(),"
                " lease_expires_at = now() - interval '1 s', attempts = %s, cancel_requested = %s"
                " WHERE id = %s",
                (attempts, cancel, job_id),
            )
    before = {outcome: sample("kka_job_leases_expired_total", outcome=outcome) for outcome in ends}

    def counted() -> dict[str, float]:
        return {
            outcome: sample("kka_job_leases_expired_total", outcome=outcome) - before[outcome]
            for outcome in ends
        }

    stop = asyncio.Event()
    running = asyncio.create_task(Worker(pool, {}, owner="sweeper", lease_s=3, poll_s=0.05).run(stop))
    deadline = asyncio.get_running_loop().time() + 5
    try:
        while counted() != dict.fromkeys(ends, 1.0) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)
    finally:
        stop.set()
        await asyncio.wait_for(running, 5)

    assert counted() == dict.fromkeys(ends, 1.0)


@pytest.fixture
async def probes() -> AsyncIterator[str]:
    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    server = probe_server()
    serving = asyncio.create_task(server.serve(sockets=[listening]))
    while not server.started:
        await asyncio.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{listening.getsockname()[1]}"
    finally:
        server.should_exit = True
        await serving


async def test_the_worker_answers_its_liveness_probe(probes: str) -> None:
    async with httpx2.AsyncClient(base_url=probes) as client:
        answer = await client.get("/health")

    assert answer.status_code == 200
    assert answer.json() == {"status": "ok"}


async def test_the_worker_serves_its_metrics(probes: str) -> None:
    async with httpx2.AsyncClient(base_url=probes) as client:
        answer = await client.get("/metrics")

    assert answer.status_code == 200
    assert "kka_jobs_total" in answer.text
    assert "kka_job_duration_seconds" in answer.text
    assert "kka_job_leases_expired_total" in answer.text


@pytest.mark.parametrize("path", ["/ready", "/api/v1/info", "/"])
async def test_the_worker_answers_nothing_else(probes: str, path: str) -> None:
    async with httpx2.AsyncClient(base_url=probes) as client:
        answer = await client.get(path)

    assert answer.status_code == 404
