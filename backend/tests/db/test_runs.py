"""The runs of the pipeline's stages (plan M1 6.6, app/db/runs.py): one for each stage and attempt of a
job, ended once with its outcome; a stage is done for a job once one of its runs is."""

from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from app.db.migrate import migrate
from app.db.runs import RunStart, Stage, done_stages, finish_run, start_run
from app.jobs.queue import account_lane, enqueue
from tests.db.l1 import CV, add_conversion, add_document, seed_vocabulary

pytestmark = [pytest.mark.pg, pytest.mark.anyio]


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as setup:
        seed_vocabulary(setup)
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


@pytest.fixture
def made(database_url: str, connection: psycopg.AsyncConnection) -> dict[str, Any]:
    with psycopg.connect(database_url, autocommit=True) as setup:
        made = add_conversion(setup)
        made["document"] = add_document(setup, made)
    return made


async def a_job(connection: psycopg.AsyncConnection, made: dict[str, Any]) -> UUID:
    return await enqueue(
        connection, "extract.run", account_lane(made["owner"]), {"document_id": str(made["document"])}
    )


def run_of(made: dict[str, Any], job: UUID, stage: Stage = "X1", attempt: int = 1) -> RunStart:
    return RunStart(
        document_id=made["document"],
        job_id=job,
        attempt=attempt,
        stage=stage,
        model="gpt-6-luna",
        prompt_version="x1-profile/1",
        profile_version="https://w3id.org/wlo/curriculum/profile/school#Terminology",
        lexicon_release=None,
    )


async def test_a_run_is_started_and_ended_once_with_what_it_made(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job = await a_job(connection, made)

    run = await start_run(connection, run_of(made, job))
    ended = await finish_run(connection, run, "done", {"headings": 3})
    again = await finish_run(connection, run, "failed")

    cursor = await connection.execute(
        "SELECT stage_iri, attempt, model, prompt_version, raw_response_key, outcome, result,"
        " finished_at IS NOT NULL FROM extraction_run WHERE id = %s",
        (run,),
    )
    assert await cursor.fetchone() == (
        CV + "stage_X1",
        1,
        "gpt-6-luna",
        "x1-profile/1",
        f"runs/{run}/x1",
        "done",
        {"headings": 3},
        True,
    )
    assert (ended, again) == (True, False)


async def test_a_stage_is_done_for_a_job_once_one_of_its_runs_is(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job, other = await a_job(connection, made), await a_job(connection, made)
    await finish_run(connection, await start_run(connection, run_of(made, job, "X1")), "done")
    await start_run(connection, run_of(made, job, "X2", attempt=1))  # cancelled with its attempt: no outcome
    await finish_run(
        connection, await start_run(connection, run_of(made, job, "X2", attempt=2)), "budget_exhausted"
    )
    await finish_run(connection, await start_run(connection, run_of(made, other, "X2")), "done")

    assert await done_stages(connection, made["document"], job) == {"X1"}
    assert await done_stages(connection, made["document"], other) == {"X2"}


def test_a_run_names_a_stage_of_the_core() -> None:
    with pytest.raises(ValueError, match="stage"):
        RunStart(
            document_id=UUID(int=1),
            job_id=None,
            attempt=None,
            stage=cast(Any, "X9"),  # what the check is for
            model=None,
            prompt_version=None,
            profile_version=None,
            lexicon_release=None,
        )
