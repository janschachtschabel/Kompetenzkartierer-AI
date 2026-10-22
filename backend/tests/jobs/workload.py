"""A worker process for the stress tests: ``python -m tests.jobs.workload URL OWNER MODE``.

record: runs test.record and test.hang jobs by writing (job, owner) to job_run, and stops once
        no such job waits or runs.
hang:   runs test.hang jobs by writing the row and then waiting forever - the test kills it.
"""

import asyncio
import sys
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app.jobs.queue import Job
from app.jobs.worker import Worker

KINDS = ("test.record", "test.hang")
LEASE_S = 3.0


async def work(url: str, owner: str, mode: str) -> None:
    async with AsyncConnectionPool(url, min_size=1, max_size=4, open=False) as pool:

        async def record(job: Job) -> dict[str, Any]:
            async with pool.connection() as connection:
                await connection.execute(
                    "INSERT INTO job_run (job_id, owner) VALUES (%s, %s)", (job.id, owner)
                )
            await asyncio.sleep(0.01)  # long enough for the other worker to claim in between
            if mode == "hang":
                await asyncio.sleep(3600)
            return {"by": owner}

        handlers = dict.fromkeys(("test.hang",) if mode == "hang" else KINDS, record)
        stop = asyncio.Event()
        worker = asyncio.create_task(
            Worker(pool, handlers, owner=owner, lease_s=LEASE_S, poll_s=0.05).run(stop)
        )
        if mode == "record":
            await _stop_when_done(pool, stop)
        await worker


async def _stop_when_done(pool: AsyncConnectionPool, stop: asyncio.Event) -> None:
    idle = 0
    while idle < 5:
        await asyncio.sleep(0.2)
        async with pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT count(*) FROM job WHERE kind = ANY(%s) AND status IN ('queued', 'running')",
                (list(KINDS),),
            )
            row = await cursor.fetchone()
        idle = idle + 1 if row and row[0] == 0 else 0
    stop.set()


if __name__ == "__main__":
    asyncio.run(work(*sys.argv[1:4]), loop_factory=asyncio.SelectorEventLoop)
