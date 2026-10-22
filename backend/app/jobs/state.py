"""A job's state as the API shows it: no payload (it may hold a URL or a file's name the
owner sent), and of the error its code only - the message is the handler's."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import class_row


@dataclass(frozen=True)
class JobState:
    id: UUID
    kind: str
    status: str
    progress: dict[str, Any] | None
    error_code: str | None
    cancel_requested: bool
    attempts: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


async def job_state(connection: psycopg.AsyncConnection, job_id: UUID, lane: str | None) -> JobState | None:
    """The job, if it is ``lane``'s (``None``: of any lane, for an admin); who may see it is
    decided in the query, a job of another lane is not loaded."""
    cursor = connection.cursor(row_factory=class_row(JobState))
    await cursor.execute(
        """
        SELECT id, kind, status, progress, error->>'code' AS error_code, cancel_requested,
            attempts, max_attempts, created_at, started_at, finished_at
        FROM job WHERE id = %(id)s AND (%(lane)s::text IS NULL OR lane = %(lane)s)
        """,
        {"id": job_id, "lane": lane},
    )
    return await cursor.fetchone()
