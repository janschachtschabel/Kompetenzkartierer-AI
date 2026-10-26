"""The runs of the pipeline's stages on a document (plan M1 6.6; table extraction_run): one for each
stage and attempt of a job, ended once with its outcome and what it made.

A stage writes its whole result in one transaction at its end, and ends its run in that same
transaction (``finish_run``): its run says done exactly when its result is there. A run without
an outcome was cancelled with its attempt or is still running; the job's next attempt starts a
run of its own, and skips the stages ``done_stages`` names.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, get_args
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.core.ids import new_id

# As migration 0017 lists them (tests/db/test_runs_schema.py)
RunOutcome = Literal["done", "failed", "budget_exhausted"]
# How a run stands as its reader sees it: its outcome, else running or left with its attempt
RunState = Literal["done", "failed", "budget_exhausted", "running", "abandoned"]
# The stages of the core's scheme cv:Stages, by their notation
Stage = Literal["X0", "X1", "X2", "X3", "X4", "X5", "X6", "N1", "N2", "G1"]
STAGES = "https://w3id.org/wlo/curriculum/vocab#Stages"
STAGE_PREFIX = "https://w3id.org/wlo/curriculum/vocab#stage_"  # of a stage's IRI, before its notation


def stage_iri(stage: Stage) -> str:
    """The IRI of a stage of cv:Stages by its notation ("X1")."""
    return STAGE_PREFIX + stage


_START = """
    INSERT INTO extraction_run (id, document_id, job_id, attempt, stage_scheme, stage_iri, model,
        prompt_version, profile_version, lexicon_release, raw_response_key)
    VALUES (%(id)s, %(document)s, %(job)s, %(attempt)s, %(scheme)s, %(stage)s, %(model)s, %(prompt)s,
        %(profile)s, %(release)s, %(raw)s)
"""
_FINISH = """
    UPDATE extraction_run SET outcome = %s, result = %s, finished_at = now()
    WHERE id = %s AND outcome IS NULL
"""
_DONE_BY = "SELECT stage_iri FROM extraction_run WHERE job_id = %s AND outcome = 'done' ORDER BY started_at"
_DONE = """
    SELECT DISTINCT stage_iri FROM extraction_run WHERE document_id = %s AND outcome = 'done'
"""
_OWED = """
SELECT EXISTS (
    SELECT FROM extraction_run WHERE document_id = %(document)s AND stage_iri = %(x6)s
        AND started_at > coalesce(
            (SELECT max(started_at) FROM extraction_run
             WHERE document_id = %(document)s AND stage_iri = %(x5)s AND outcome = 'done'),
            '-infinity'
        )
)
"""


@dataclass(frozen=True)
class RunStart:
    """What a run of ``stage`` says of itself from its start: the job and attempt it runs in, and
    the model, prompt, profile and lexicon release it reads with."""

    document_id: UUID
    job_id: UUID | None
    attempt: int | None
    stage: Stage
    model: str | None
    prompt_version: str | None
    profile_version: str | None
    lexicon_release: int | None

    def __post_init__(self) -> None:
        if self.stage not in get_args(Stage):
            raise ValueError(f"{self.stage!r} is no stage of the core (X0 to X6, N1, N2, G1)")


async def start_run(connection: psycopg.AsyncConnection, run: RunStart) -> UUID:
    """A new run of the stage, not ended; its raw answers lie under ``runs/<run>/<stage>``
    (app/llm/raw.py), as its row says."""
    run_id = new_id()
    async with connection.transaction():
        await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'extraction_run')", (run_id,))
        await connection.execute(
            _START,
            {
                "id": run_id,
                "document": run.document_id,
                "job": run.job_id,
                "attempt": run.attempt,
                "scheme": STAGES,
                "stage": stage_iri(run.stage),
                "model": run.model,
                "prompt": run.prompt_version,
                "profile": run.profile_version,
                "release": run.lexicon_release,
                "raw": f"runs/{run_id}/{run.stage.lower()}",
            },
        )
    return run_id


async def finish_run(
    connection: psycopg.AsyncConnection,
    run_id: UUID,
    outcome: RunOutcome,
    result: dict[str, Any] | None = None,
) -> bool:
    """End the run with ``outcome`` and what it made, in the caller's transaction - the one that
    writes the stage's result; False where it had ended already, and nothing changes."""
    cursor = await connection.execute(
        _FINISH, (outcome, Jsonb(result) if result is not None else None, run_id)
    )
    return cursor.rowcount == 1


async def stage_result(
    connection: psycopg.AsyncConnection, document_id: UUID, stage: Stage
) -> dict[str, Any] | None:
    """What the last run of ``stage`` done on the document made, where one is done."""
    cursor = await connection.execute(
        "SELECT result FROM extraction_run WHERE document_id = %s AND stage_iri = %s AND outcome = 'done'"
        " ORDER BY finished_at DESC LIMIT 1",
        (document_id, stage_iri(stage)),
    )
    found = await cursor.fetchone()
    return None if found is None else found[0]


async def done_stages(connection: psycopg.AsyncConnection, document_id: UUID) -> set[str]:
    """The stages done on the document, by notation ("X1"), whichever job did them: a job after one
    that ended for good goes on where it stopped."""
    cursor = await connection.execute(_DONE, (document_id,))
    return {iri.removeprefix(STAGE_PREFIX) for (iri,) in await cursor.fetchall()}


async def stages_done_by(connection: psycopg.AsyncConnection, job_id: UUID) -> list[str]:
    """The stages the job's runs did, by notation, in the order they began: where an attempt of a job
    that runs a stage more than once (extract.repair) goes on."""
    cursor = await connection.execute(_DONE_BY, (job_id,))
    return [iri.removeprefix(STAGE_PREFIX) for (iri,) in await cursor.fetchall()]


async def x5_owed(connection: psycopg.AsyncConnection, document_id: UUID) -> bool:
    """Whether X5 owes the document a check: a run of X6 began after its last run of X5 that ended done -
    whatever became of the repair, it may have written (app/pipeline/x6_repair.py)."""
    cursor = await connection.execute(
        _OWED, {"document": document_id, "x5": stage_iri("X5"), "x6": stage_iri("X6")}
    )
    found = await cursor.fetchone()
    return bool(found and found[0])


async def lock_for_stage(connection: psycopg.AsyncConnection, document_id: UUID, stage: Stage) -> bool:
    """Lock the document for a stage's write, in the caller's transaction, and say whether a run of
    the stage is done on it - another job's, since this one looked: the stage then writes nothing.
    A second job that asked meanwhile waits for the first one's commit here, then sees its run
    (read committed); as X1's write does (app/db/profile.py, lock_for_x1)."""
    await connection.execute("SELECT 1 FROM document WHERE id = %s FOR NO KEY UPDATE", (document_id,))
    return stage in await done_stages(connection, document_id)


@dataclass(frozen=True)
class RunView:
    stage: str  # its notation, "X1"
    attempt: int | None
    state: RunState
    started_at: datetime
    finished_at: datetime | None
    failure: str | None  # what broke a failed run, by its type ("LeaseLost")


# a run without an outcome runs while its job runs that very attempt and began no run since - a
# release counts the attempt back, so the next claim runs its number again; otherwise it was left
_RUNS = """
SELECT r.stage_iri, r.attempt, r.outcome, r.started_at, r.finished_at, r.result ->> 'failure',
    j.status = 'running' AND j.attempts = r.attempt AND NOT EXISTS (
        SELECT 1 FROM extraction_run later
        WHERE later.job_id = r.job_id AND (later.started_at, later.id) > (r.started_at, r.id))
FROM extraction_run r LEFT JOIN job j ON j.id = r.job_id
WHERE r.document_id = %s ORDER BY r.started_at, r.id
"""


async def runs_of(connection: psycopg.AsyncConnection, document_id: UUID) -> list[RunView]:
    """The document's runs in the order they began, each with how it stands."""
    cursor = await connection.execute(_RUNS, (document_id,))
    return [
        RunView(
            stage=iri.removeprefix(STAGE_PREFIX),
            attempt=attempt,
            state=outcome or ("running" if running else "abandoned"),
            started_at=started,
            finished_at=finished,
            failure=failure,
        )
        for iri, attempt, outcome, started, finished, failure, running in await cursor.fetchall()
    ]
