"""The runs of the pipeline's stages (plan M1 6.6, app/db/runs.py): one for each stage and attempt of a
job, ended once with its outcome; a stage is done for a job once one of its runs is."""

from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from app.db.migrate import migrate
from app.db.runs import RunOutcome, RunStart, Stage, done_stages, finish_run, runs_of, stage_result, start_run
from app.jobs.queue import account_lane, claim, enqueue, release
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


async def test_a_stage_is_done_for_a_document_once_a_run_of_any_job_is(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job, other = await a_job(connection, made), await a_job(connection, made)
    await finish_run(connection, await start_run(connection, run_of(made, job, "X1")), "done")
    await start_run(connection, run_of(made, job, "X2", attempt=1))  # cancelled with its attempt: no outcome
    await finish_run(
        connection, await start_run(connection, run_of(made, job, "X2", attempt=2)), "budget_exhausted"
    )
    await finish_run(connection, await start_run(connection, run_of(made, other, "X2")), "done")

    assert await done_stages(connection, made["document"]) == {"X1", "X2"}
    await finish_run(connection, await start_run(connection, run_of(made, job, "X4")), "failed")
    assert await done_stages(connection, made["document"]) == {"X1", "X2"}  # a failed run is no done stage


async def test_a_stage_s_result_is_what_its_last_done_run_made(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job, other = await a_job(connection, made), await a_job(connection, made)
    runs: list[tuple[RunStart, RunOutcome, dict[str, int]]] = [
        (run_of(made, job, "X2"), "done", {"units": 3}),
        (run_of(made, other, "X2"), "done", {"units": 5}),
        (run_of(made, other, "X2", 2), "failed", {"units": 7}),
        (run_of(made, job, "X1"), "failed", {"asked": 1}),
    ]
    for run, outcome, made_by_it in runs:
        await finish_run(connection, await start_run(connection, run), outcome, made_by_it)

    assert await stage_result(connection, made["document"], "X2") == {"units": 5}
    assert await stage_result(connection, made["document"], "X1") is None  # no run of it is done


async def test_a_document_s_runs_are_read_with_their_state_in_the_order_they_began(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    # a run without an outcome runs only while its job runs that very attempt; else it was left
    ended, running = await a_job(connection, made), await a_job(connection, made)
    finished = [
        (run_of(made, ended, "X1"), "done", {}),
        (run_of(made, ended, "X2"), "failed", {"failure": "LeaseLost"}),
        (run_of(made, ended, "X2", attempt=2), "budget_exhausted", {}),
    ]
    for run, outcome, made_by_it in finished:
        await finish_run(connection, await start_run(connection, run), cast(RunOutcome, outcome), made_by_it)
    await start_run(connection, run_of(made, ended, "X2", attempt=3))  # its job was cancelled
    await connection.execute(
        "UPDATE job SET status = 'cancelled', finished_at = now() WHERE id = %s", (ended,)
    )
    await connection.execute(
        "UPDATE job SET status = 'running', attempts = 2, lease_owner = 'w1',"
        " lease_token = gen_random_uuid(), lease_expires_at = now() + interval '1 minute' WHERE id = %s",
        (running,),
    )
    await start_run(connection, run_of(made, running, "X1", attempt=1))  # an attempt before: left
    await start_run(connection, run_of(made, running, "X1", attempt=2))

    runs = await runs_of(connection, made["document"])

    assert [(run.stage, run.attempt, run.state, run.failure, run.finished_at is None) for run in runs] == [
        ("X1", 1, "done", None, False),
        ("X2", 1, "failed", "LeaseLost", False),
        ("X2", 2, "budget_exhausted", None, False),
        ("X2", 3, "abandoned", None, True),
        ("X1", 1, "abandoned", None, True),
        ("X1", 2, "running", None, True),
    ]
    assert await runs_of(connection, UUID(int=1)) == []


async def test_a_run_of_an_attempt_handed_back_does_not_run_beside_the_next_of_its_number(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    # a stopping worker's release counts the attempt back: the next claim runs its number again
    job = await a_job(connection, made)
    for worker in ("w1", "w2"):
        claimed = await claim(connection, worker, ("extract.run",), 30)
        assert claimed is not None and claimed.attempts == 1
        await start_run(connection, run_of(made, job, "X1", attempt=claimed.attempts))
        if worker == "w1":
            await release(connection, claimed)
    # begun in one moment, the one begun after by id runs; another job's run is not this one's
    await connection.execute("UPDATE extraction_run SET started_at = now() - interval '1 minute'")
    await start_run(connection, run_of(made, await a_job(connection, made), "X2"))

    runs = await runs_of(connection, made["document"])

    assert [(run.attempt, run.state) for run in runs] == [(1, "abandoned"), (1, "running"), (1, "abandoned")]


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
