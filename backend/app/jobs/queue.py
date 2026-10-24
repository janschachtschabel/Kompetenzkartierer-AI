"""The job queue on the ``job`` table.

Lanes (accounts) take turns: a claim picks the lane with the fewest running jobs, then the
one served longest ago, then the one with the oldest waiting job, and takes that lane's oldest
job with ``FOR UPDATE SKIP LOCKED``, so workers never take the same one. One account with many
jobs does not hold back the others, with one worker or many. The claim sets a lease with a
token of its own; the worker renews it with ``heartbeat`` and learns there of a requested
cancel. Only the claim holding the lease can finish a job: a worker that lost its lease (too
slow, cut off) gets ``LeaseLost`` and must drop its result, another worker has the job by then.
``requeue_expired`` hands expired leases back to the queue while attempts remain. A job keeps
the trace id of the request that enqueued it and reports its progress under its lease
(``report_progress``). A job may carry a unique key no two waiting or running jobs share
(migration 0018): ``enqueue`` of a key whose job is open raises ``OpenJob`` with that job.
Each function is one statement, or one transaction (``claim``), so it holds on any connection
- but ``enqueue`` of a key, which looks for the open job after its insert gave way; every time
is the database's ``now()``.
"""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.ids import new_id
from app.core.tracing import MAX_TRACE_CHARS, REQUEST_ID, outgoing_headers, trace_id

# What the column trace_id takes (migration 0005)
_STORABLE_TRACE = re.compile(f"[A-Za-z0-9._:@+/=,-]{{1,{MAX_TRACE_CHARS}}}")

# Wait before the next attempt: 10 s, 20 s, 40 s, ... at most 10 min. The exponent stops at 6,
# past the cap anyway: a large one overflowed and failed the sweep for every job
_BACKOFF = "make_interval(secs => least(10 * power(2, least(greatest(attempts - 1, 0), 6)), 600))"
# How many lanes one claim tries when other claims are taking their jobs at the same moment
LANES_PER_CLAIM = 20
# When a claim last served the lane; skipped where another claim holds the row, which would make
# this claim - and through it every worker - wait for that one to commit
_STAMP = (
    "UPDATE job_lane SET served_at = now()"
    " WHERE lane = (SELECT lane FROM job_lane WHERE lane = %s FOR NO KEY UPDATE SKIP LOCKED)"
)
# The lanes with a job to take, in turn. Each lane's next job comes off the index on
# (lane, created_at): a long queue costs no sort.
# simplify: every lane that ever had a job is looked at, so a claim grows with the accounts that
# ever enqueued (20,000 lanes: 53 ms); later read only lanes with waiting jobs (a skip scan over
# job_waiting) or clear lanes that stayed empty
_LANES_IN_TURN = """
    SELECT job_lane.lane FROM job_lane
    CROSS JOIN LATERAL (
        SELECT job.created_at FROM job
        WHERE job.lane = job_lane.lane AND job.status = 'queued' AND job.run_after <= now()
            AND job.kind = ANY(%(kinds)s)
        ORDER BY job.created_at LIMIT 1
    ) AS next
    CROSS JOIN LATERAL (
        SELECT count(*) AS jobs FROM job WHERE job.lane = job_lane.lane AND job.status = 'running'
    ) AS running
    ORDER BY running.jobs, job_lane.served_at NULLS FIRST, next.created_at
    LIMIT %(lanes)s
"""
# The lane's oldest waiting job, now running; each attempt starts without the last one's progress
_TAKE = """
    WITH chosen AS (
        SELECT id FROM job
        WHERE lane = %(lane)s AND status = 'queued' AND run_after <= now() AND kind = ANY(%(kinds)s)
        ORDER BY created_at LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE job SET status = 'running', lease_owner = %(owner)s, lease_token = %(token)s,
        lease_expires_at = now() + make_interval(secs => %(lease)s),
        attempts = job.attempts + 1, started_at = coalesce(job.started_at, now()),
        progress = NULL
    FROM chosen WHERE job.id = chosen.id
    RETURNING job.id, job.kind, job.lane, job.payload, job.attempts, job.max_attempts,
        job.lease_owner, job.lease_token, job.trace_id
"""


class OpenJob(Exception):
    """A job of the key is waiting or running: ``job_id``. None is made beside it."""

    def __init__(self, job_id: UUID) -> None:
        super().__init__(f"job {job_id} of the key is waiting or running")
        self.job_id = job_id


JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]


class LeaseLost(Exception):
    """The job's lease is no longer this worker's: it expired, or the job ended."""


_KEY_TRIES = 3
_ENQUEUE = """
    WITH known AS (
        -- only a lane nobody has: ON CONFLICT alone waited on a claim stamping the lane
        INSERT INTO job_lane (lane) SELECT %(lane)s
        WHERE NOT EXISTS (SELECT 1 FROM job_lane WHERE lane = %(lane)s)
        ON CONFLICT DO NOTHING
    )
    INSERT INTO job (id, kind, lane, payload, max_attempts, run_after, trace_id, unique_key)
    VALUES (%(id)s, %(kind)s, %(lane)s, %(payload)s, %(attempts)s,
        now() + make_interval(secs => %(after)s), %(trace)s, %(key)s)
    ON CONFLICT (unique_key) WHERE unique_key IS NOT NULL AND status IN ('queued', 'running')
    DO NOTHING
    RETURNING id
"""


@dataclass(frozen=True)
class Job:
    id: UUID
    kind: str
    lane: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    lease_owner: str
    lease_token: UUID
    trace_id: str | None  # of the request that made the job


def account_lane(account_id: UUID) -> str:
    """The lane of the jobs an account starts: whose turn it is, and who may follow them."""
    return str(account_id)


async def enqueue(
    connection: psycopg.AsyncConnection,
    kind: str,
    lane: str,
    payload: dict[str, Any] | None = None,
    *,
    max_attempts: int = 3,
    run_after_s: float = 0,
    unique_key: str | None = None,
) -> UUID:
    """A new waiting job; ``max_attempts`` is 1 to 100. It keeps the trace id of the request
    being served, if any - without a tracing header its request id: the worker writes the
    job's lines with it. With ``unique_key`` (1 to 200 signs) and a job of that key waiting
    or running, none is made: ``OpenJob`` names that one. A start beside it in another
    transaction waits on its row in the unique index, then gives way to it or, rolled back,
    takes the key - under read committed, as a model job's admission has it; a stricter
    isolation raises psycopg's SerializationFailure there instead."""
    job_id = new_id()
    values = {
        "id": job_id,
        "kind": kind,
        "lane": lane,
        "payload": Jsonb(payload or {}),
        "attempts": max_attempts,
        "after": run_after_s,
        "trace": _request_trace(),
        "key": unique_key,
    }
    # the open job may end between the insert that gave way and the look for it: once more
    for _ in range(_KEY_TRIES):
        cursor = await connection.execute(_ENQUEUE, values)
        if await cursor.fetchone() is not None:
            return job_id
        assert unique_key is not None  # noqa: S101 - only a key's open job makes the insert give way
        if (open_id := await open_job(connection, unique_key)) is not None:
            raise OpenJob(open_id)
    raise RuntimeError(f"the open job of {unique_key!r} kept ending while a new one was asked")


async def open_job(connection: psycopg.AsyncConnection, unique_key: str) -> UUID | None:
    """The job of the key waiting or running, if any."""
    cursor = await connection.execute(
        "SELECT id FROM job WHERE unique_key = %s AND status IN ('queued', 'running')", (unique_key,)
    )
    found = await cursor.fetchone()
    return None if found is None else found[0]


# the latest job of each key (index job_by_key), by when it was made
_LATEST = """
SELECT DISTINCT ON (unique_key) unique_key, id, status, error->>'code' FROM job WHERE unique_key = ANY(%s)
ORDER BY unique_key, created_at DESC, id DESC
"""


async def open_jobs(connection: psycopg.AsyncConnection, unique_keys: Sequence[str]) -> dict[str, UUID]:
    """The job of each key waiting or running; a key without one is not there."""
    cursor = await connection.execute(
        "SELECT unique_key, id FROM job WHERE unique_key = ANY(%s) AND status IN ('queued', 'running')",
        (list(unique_keys),),
    )
    return {key: job_id for key, job_id in await cursor.fetchall()}


@dataclass(frozen=True)
class LatestJob:
    id: UUID
    status: JobStatus
    error_code: str | None  # why it failed, where it did


async def last_jobs(connection: psycopg.AsyncConnection, unique_keys: Sequence[str]) -> dict[str, LatestJob]:
    """Each key's latest job, whatever became of it; a key before its first is not there."""
    cursor = await connection.execute(_LATEST, (list(unique_keys),))
    return {key: LatestJob(job_id, status, code) for key, job_id, status, code in await cursor.fetchall()}


def _request_trace() -> str | None:
    """The trace id of the request being served, else its request id (the SPA sends no tracing
    header), as the column takes it; ``None`` outside a request, or for an id it would refuse."""
    found = trace_id() or outgoing_headers().get(REQUEST_ID)
    return found if found and _STORABLE_TRACE.fullmatch(found) else None


async def claim(
    connection: psycopg.AsyncConnection, owner: str, kinds: Collection[str], lease_s: float
) -> Job | None:
    """One waiting job of ``kinds``, now running under a new lease of ``owner``; ``None`` if none waits.

    A lane whose waiting jobs other claims are taking at this moment is passed over; when the
    first LANES_PER_CLAIM lanes are all taken, the claim finds nothing until the next poll. A
    lane another claim is stamping keeps that claim's stamp: nothing here waits on a lock.
    """
    values = {"kinds": list(kinds), "owner": owner, "lease": lease_s, "lanes": LANES_PER_CLAIM}
    async with connection.transaction():
        cursor = await connection.execute(_LANES_IN_TURN, values)
        lanes = [lane for (lane,) in await cursor.fetchall()]
        taking = connection.cursor(row_factory=dict_row)
        for lane in lanes:
            await taking.execute(_TAKE, {**values, "lane": lane, "token": new_id()})
            found = await taking.fetchone()
            if found is not None:
                await connection.execute(_STAMP, (lane,))
                return Job(**found)
    return None


async def heartbeat(connection: psycopg.AsyncConnection, job: Job, lease_s: float) -> bool:
    """Renew the lease; ``True`` if a cancel was requested. Raises ``LeaseLost``."""
    cursor = await connection.execute(
        "UPDATE job SET lease_expires_at = now() + make_interval(secs => %s)"
        " WHERE id = %s AND lease_token = %s AND status = 'running' RETURNING cancel_requested",
        (lease_s, job.id, job.lease_token),
    )
    found = await cursor.fetchone()
    if found is None:
        raise LeaseLost(str(job.id))
    return bool(found[0])


_HELD = (
    "SELECT 1 FROM job WHERE id = %s AND lease_token = %s AND status = 'running' AND lease_expires_at > now()"
)


async def hold_lease(connection: psycopg.AsyncConnection, job: Job) -> None:
    """Lock the job's row for the caller's transaction while the attempt holds its lease, so what
    the transaction writes is the attempt's: a sweep that would hand the job back, or another
    end of it, waits for the commit. Raises ``LeaseLost`` where the lease is gone or ran out."""
    cursor = await connection.execute(f"{_HELD} FOR NO KEY UPDATE", (job.id, job.lease_token))
    if await cursor.fetchone() is None:
        raise LeaseLost(str(job.id))


async def check_lease(connection: psycopg.AsyncConnection, job: Job) -> None:
    """Raise ``LeaseLost`` unless the attempt still holds its lease: looked at before work that
    costs - a model's request - so a handler left to unwind after its job ended, cancelled or
    lost, spends nothing more."""
    cursor = await connection.execute(_HELD, (job.id, job.lease_token))
    if await cursor.fetchone() is None:
        raise LeaseLost(str(job.id))


async def report_progress(
    connection: psycopg.AsyncConnection, job: Job, code: str, params: dict[str, Any]
) -> None:
    """Note how far the job has come (a code the interface words, and its parameters). Raises
    ``LeaseLost`` when the lease is no longer this worker's: the job is another's by then."""
    cursor = await connection.execute(
        "UPDATE job SET progress = %s WHERE id = %s AND lease_token = %s AND status = 'running' RETURNING id",
        (Jsonb({"code": code, "params": params}), job.id, job.lease_token),
    )
    if await cursor.fetchone() is None:
        raise LeaseLost(str(job.id))


async def complete(connection: psycopg.AsyncConnection, job: Job, result: dict[str, Any] | None) -> None:
    await _finish(connection, job, "status = 'done', result = %s", (Jsonb(result),))


async def mark_cancelled(connection: psycopg.AsyncConnection, job: Job) -> None:
    await _finish(connection, job, "status = 'cancelled'", ())


async def fail(
    connection: psycopg.AsyncConnection, job: Job, code: str, message: str, *, retry: bool
) -> Literal["queued", "failed", "cancelled"]:
    """Record the failure; the job waits for another attempt if ``retry`` and attempts remain.

    A job whose cancel was asked for ends cancelled: that is what its owner wanted.
    """
    cursor = await connection.execute(
        f"""
        UPDATE job SET error = %(error)s, lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
            status = CASE WHEN cancel_requested THEN 'cancelled'
                          WHEN %(retry)s AND attempts < max_attempts THEN 'queued' ELSE 'failed' END,
            run_after = CASE WHEN %(retry)s THEN now() + {_BACKOFF} ELSE run_after END,
            finished_at = CASE WHEN NOT cancel_requested AND %(retry)s AND attempts < max_attempts
                               THEN NULL ELSE now() END
        WHERE id = %(id)s AND lease_token = %(token)s AND status = 'running'
        RETURNING status
        """,  # noqa: S608 - _BACKOFF is a constant expression
        {
            "error": Jsonb({"code": _storable(code), "message": _storable(message)}),
            "retry": retry,
            "id": job.id,
            "token": job.lease_token,
        },
    )
    found = await cursor.fetchone()
    if found is None:
        raise LeaseLost(str(job.id))
    status: Literal["queued", "failed", "cancelled"] = found[0]
    return status


async def release(connection: psycopg.AsyncConnection, job: Job) -> None:
    """Give a running job back unspent, for the next worker: its attempt is not counted.

    A stopping worker does this with a job that outlasted its grace; one asked to cancel ends.
    """
    cursor = await connection.execute(
        """
        UPDATE job SET lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
            status = CASE WHEN cancel_requested THEN 'cancelled' ELSE 'queued' END,
            attempts = CASE WHEN cancel_requested THEN attempts ELSE greatest(attempts - 1, 0) END,
            run_after = now(),
            finished_at = CASE WHEN cancel_requested THEN now() END
        WHERE id = %s AND lease_token = %s AND status = 'running'
        RETURNING id
        """,
        (job.id, job.lease_token),
    )
    if await cursor.fetchone() is None:
        raise LeaseLost(str(job.id))


def _storable(text: str) -> str:
    """``text`` as jsonb takes it: a NUL or a lone surrogate - a handler's message may quote
    input - made the database refuse the failure, and the job stayed running."""
    return text.replace("\x00", "\ufffd").encode("utf-8", "replace").decode("utf-8")


async def request_cancel(connection: psycopg.AsyncConnection, job_id: UUID, lane: str | None) -> bool:
    """Mark a waiting or running job of ``lane`` for cancelling (``None``: of any lane, for an
    admin); a waiting one ends now. ``False`` if it had ended or is another lane's."""
    cursor = await connection.execute(
        """
        UPDATE job SET cancel_requested = true,
            status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
            finished_at = CASE WHEN status = 'queued' THEN now() ELSE finished_at END
        WHERE id = %(id)s AND status IN ('queued', 'running')
            AND (%(lane)s::text IS NULL OR lane = %(lane)s)
        RETURNING id
        """,
        {"id": job_id, "lane": lane},
    )
    return await cursor.fetchone() is not None


async def requeue_expired(
    connection: psycopg.AsyncConnection,
) -> list[Literal["queued", "failed", "cancelled"]]:
    """Hand jobs whose lease expired back to the queue, or end them; what became of each."""
    cursor = await connection.execute(
        f"""
        UPDATE job SET lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,
            status = CASE WHEN cancel_requested THEN 'cancelled'
                          WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
            run_after = now() + {_BACKOFF},
            error = CASE WHEN cancel_requested OR attempts < max_attempts THEN error
                         ELSE jsonb_build_object('code', 'lease_lost',
                              'message', 'the worker stopped renewing its lease') END,
            finished_at = CASE WHEN NOT cancel_requested AND attempts < max_attempts THEN NULL ELSE now() END
        WHERE status = 'running' AND lease_expires_at < now()
        RETURNING status
        """  # noqa: S608 - _BACKOFF is a constant expression
    )
    return [status for (status,) in await cursor.fetchall()]


async def _finish(
    connection: psycopg.AsyncConnection, job: Job, assignment: str, values: tuple[Any, ...]
) -> None:
    cursor = await connection.execute(
        f"UPDATE job SET {assignment}, lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL,"  # noqa: S608
        " finished_at = now() WHERE id = %s AND lease_token = %s AND status = 'running' RETURNING id",
        (*values, job.id, job.lease_token),
    )
    if await cursor.fetchone() is None:
        raise LeaseLost(str(job.id))
