"""The worker counts its jobs by kind and ending, times them, and answers /health and /metrics
on its internal port: the cluster's liveness probe and Prometheus ask there."""

import asyncio
import socket
from collections.abc import AsyncIterator
from typing import Any

import httpx2
import pytest
from prometheus_client import REGISTRY
from psycopg_pool import AsyncConnectionPool

from app.db.migrate import migrate
from app.jobs.probes import probe_server
from app.jobs.queue import Job, enqueue, request_cancel
from app.jobs.worker import Handler, PermanentError, Worker

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
                await request_cancel(connection, job_id)
            else:  # another worker's claim now
                steal = "UPDATE job SET lease_token = gen_random_uuid() WHERE id = %s"
                await connection.execute(steal, (job_id,))

    counted = sample("kka_jobs_total", kind=kind, outcome=ending)
    # a lease of 3 s is renewed every second: the worker learns of the cancel or the loss then
    await asyncio.gather(Worker(pool, {kind: waits}, owner="w1", lease_s=3).run_once(), interrupt())

    assert sample("kka_jobs_total", kind=kind, outcome=ending) == counted + 1


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


@pytest.mark.parametrize("path", ["/ready", "/api/v1/info", "/"])
async def test_the_worker_answers_nothing_else(probes: str, path: str) -> None:
    async with httpx2.AsyncClient(base_url=probes) as client:
        answer = await client.get(path)

    assert answer.status_code == 404
