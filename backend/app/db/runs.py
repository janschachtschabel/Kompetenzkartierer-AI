"""The runs of the pipeline's stages on a document (plan M1 6.6; table extraction_run): one for each
stage and attempt of a job, ended once with its outcome and what it made.

A stage writes its whole result in one transaction at its end, and ends its run in that same
transaction (``finish_run``): its run says done exactly when its result is there. A run without
an outcome was cancelled with its attempt or is still running; the job's next attempt starts a
run of its own, and skips the stages ``done_stages`` names.
"""

from dataclasses import dataclass
from typing import Any, Literal, get_args
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.core.ids import new_id

# As migration 0017 lists them (tests/db/test_runs_schema.py)
RunOutcome = Literal["done", "failed", "budget_exhausted"]
# The stages of the core's scheme cv:Stages, by their notation
Stage = Literal["X0", "X1", "X2", "X3", "X4", "X5", "X6", "N1", "N2", "G1"]
STAGES = "https://w3id.org/wlo/curriculum/vocab#Stages"
_STAGE_IRI = "https://w3id.org/wlo/curriculum/vocab#stage_"


def stage_iri(stage: Stage) -> str:
    """The IRI of a stage of cv:Stages by its notation ("X1")."""
    return _STAGE_IRI + stage


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
_DONE = """
    SELECT DISTINCT stage_iri FROM extraction_run WHERE document_id = %s AND outcome = 'done'
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
    return {iri.removeprefix(_STAGE_IRI) for (iri,) in await cursor.fetchall()}
