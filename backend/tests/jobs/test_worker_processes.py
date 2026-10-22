"""Two worker processes on one queue: each job runs once, a dead worker's job is taken over."""

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.db.migrate import migrate
from app.jobs.queue import enqueue, request_cancel

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

BACKEND = Path(__file__).resolve().parents[2]
DEADLINE_S = 90


def start(url: str, owner: str, mode: str) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S603 - this interpreter and a fixed module
        [sys.executable, "-m", "tests.jobs.workload", url, owner, mode],
        cwd=BACKEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def fetch(url: str, query: str, *params: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(url) as connection:
        return connection.execute(query, params).fetchall()


def wait_for(url: str, query: str, *params: Any) -> None:
    deadline = time.monotonic() + DEADLINE_S
    while not fetch(url, query, *params)[0][0]:
        assert time.monotonic() < deadline, f"timed out waiting for: {query}"
        time.sleep(0.1)


@pytest.fixture
def queue_db(database_url: str) -> str:
    migrate(database_url)
    with psycopg.connect(database_url) as connection:
        connection.execute("CREATE TABLE job_run (job_id uuid NOT NULL, owner text NOT NULL)")
    return database_url


async def enqueue_jobs(url: str, kind: str, count: int, lanes: int = 3) -> list[object]:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as connection:
        return [await enqueue(connection, kind, f"account-{index % lanes}") for index in range(count)]


async def test_two_workers_run_fifty_jobs_each_exactly_once(queue_db: str) -> None:
    await enqueue_jobs(queue_db, "test.record", 50)
    cancelled = await enqueue_jobs(queue_db, "test.record", 5)
    async with await psycopg.AsyncConnection.connect(queue_db, autocommit=True) as connection:
        for job_id in cancelled:
            await request_cancel(connection, job_id)  # type: ignore[arg-type]

    workers = [start(queue_db, owner, "record") for owner in ("w1", "w2")]
    outputs = [worker.communicate(timeout=DEADLINE_S)[0] for worker in workers]

    assert [worker.returncode for worker in workers] == [0, 0], outputs
    [(runs, distinct)] = fetch(queue_db, "SELECT count(*), count(DISTINCT job_id) FROM job_run")
    assert (runs, distinct) == (50, 50)
    assert fetch(queue_db, "SELECT count(*) FROM job WHERE status = 'done'") == [(50,)]
    assert fetch(queue_db, "SELECT count(*) FROM job_run WHERE job_id = ANY(%s)", cancelled) == [(0,)]


async def test_a_job_of_a_worker_that_died_is_taken_over(queue_db: str) -> None:
    [job_id] = await enqueue_jobs(queue_db, "test.hang", 1)
    dying = start(queue_db, "dying", "hang")
    try:
        wait_for(queue_db, "SELECT count(*) FROM job_run WHERE owner = 'dying'")
    finally:
        dying.kill()  # no heartbeat any more, no goodbye
        dying.communicate(timeout=30)
    rescuer = start(queue_db, "rescuer", "record")
    try:
        # the rescuer hands the expired lease back; skip the backoff instead of waiting it out
        wait_for(queue_db, "SELECT count(*) FROM job WHERE id = %s AND status = 'queued'", job_id)
        fetch_and_commit = "UPDATE job SET run_after = now() WHERE id = %s RETURNING id"
        fetch(queue_db, fetch_and_commit, job_id)
        output = rescuer.communicate(timeout=DEADLINE_S)[0]
    finally:
        if rescuer.poll() is None:
            rescuer.kill()

    assert rescuer.returncode == 0, output
    assert fetch(queue_db, "SELECT status, attempts, result FROM job WHERE id = %s", job_id) == [
        ("done", 2, {"by": "rescuer"})
    ]
