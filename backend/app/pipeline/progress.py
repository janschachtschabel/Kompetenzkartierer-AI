"""How far an extraction has come, as its job reports it (plan M1 6.6): a code the interface words
(frontend JobProgress.vue, ``jobs.progress.<code>``; a test holds the two to each other) with its
parameters, numbers only, reported before the slow step it names and only forward."""

from typing import Literal

import psycopg

from app.jobs.queue import Job, report_progress

ProgressCode = Literal["extract_profile", "extract_outline", "extract_segments"]


async def report(connection: psycopg.AsyncConnection, job: Job, code: ProgressCode, **params: int) -> None:
    """Note the step the job takes now; LeaseLost where the job is another attempt's."""
    await report_progress(connection, job, code, dict(params))
