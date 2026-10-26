"""The runs of the pipeline's stages (plan M1 6.6, app/db/runs.py): one for each stage and attempt of a
job, ended once with its outcome; a stage is done for a job once one of its runs is."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from app.db.migrate import migrate
from app.db.runs import (
    RunOutcome,
    RunStart,
    Stage,
    done_stages,
    finish_run,
    lock_for_stage,
    runs_of,
    stage_result,
    start_run,
    x5_owed,
)
from app.jobs.queue import account_lane, claim, enqueue, release
from tests.db.l1 import CV, add_conversion, add_document, seed_vocabulary
from tests.support import waiting_on_a_lock

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


async def test_a_check_is_owed_once_a_repair_began_after_the_document_s_last_one(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job, document = await a_job(connection, made), made["document"]

    assert await x5_owed(connection, document) is False  # nothing checked, nothing repaired
    await finish_run(connection, await start_run(connection, run_of(made, job, "X5")), "done")
    assert await x5_owed(connection, document) is False
    await finish_run(connection, await start_run(connection, run_of(made, job, "X5", attempt=4)), "failed")
    assert await x5_owed(connection, document) is False  # only a repair owes one: it wrote
    await start_run(connection, run_of(made, job, "X6"))  # broken off: it may have written all the same
    assert await x5_owed(connection, document) is True
    await finish_run(connection, await start_run(connection, run_of(made, job, "X5", attempt=2)), "failed")
    assert await x5_owed(connection, document) is True  # a check that failed is none
    await finish_run(connection, await start_run(connection, run_of(made, job, "X5", attempt=3)), "done")
    assert await x5_owed(connection, document) is False


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


async def test_a_stage_s_write_locks_the_document_and_says_whether_another_run_did_it(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job = await a_job(connection, made)
    await finish_run(connection, await start_run(connection, run_of(made, job, "X2")), "done")

    async with connection.transaction():
        assert await lock_for_stage(connection, made["document"], "X3") is False
    await finish_run(connection, await start_run(connection, run_of(made, job, "X3")), "done")
    async with connection.transaction():
        assert await lock_for_stage(connection, made["document"], "X3") is True


async def test_a_second_writer_of_a_stage_waits_for_the_first_and_then_sees_its_run(
    database_url: str, connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job = await a_job(connection, made)
    run = await start_run(connection, run_of(made, job, "X3"))
    first = await psycopg.AsyncConnection.connect(database_url)
    second = await psycopg.AsyncConnection.connect(database_url)
    try:
        assert await lock_for_stage(first, made["document"], "X3") is False

        async def second_writer() -> bool:
            async with second.transaction():
                return await lock_for_stage(second, made["document"], "X3")

        writing = asyncio.create_task(second_writer())
        await waiting_on_a_lock(connection, second.info.backend_pid)
        await finish_run(first, run, "done")
        await first.commit()

        assert await asyncio.wait_for(writing, 10) is True
    finally:
        await first.close()
        await second.close()


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


async def test_a_check_is_owed_once_an_editor_changed_the_document_after_its_last_one(
    connection: psycopg.AsyncConnection, made: dict[str, Any]
) -> None:
    job, document = await a_job(connection, made), made["document"]
    edited = "UPDATE document SET edited_at = now() WHERE id = %s"

    await connection.execute(edited, (document,))
    assert await x5_owed(connection, document) is True  # changed, and never checked since
    await finish_run(connection, await start_run(connection, run_of(made, job, "X5")), "done")
    assert await x5_owed(connection, document) is False  # the check began after the change
    await connection.execute(edited, (document,))
    assert await x5_owed(connection, document) is True
    await finish_run(connection, await start_run(connection, run_of(made, job, "X5", attempt=2)), "done")
    assert await x5_owed(connection, document) is False
