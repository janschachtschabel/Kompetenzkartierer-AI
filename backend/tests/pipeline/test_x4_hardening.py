"""X4 in the job extract.run where something breaks (plan M1 7b, F11; review 7b C1-C6): a unit no window
fits ends the job before any unit is asked; an error in one unit ends the others asking beside it, the
error the job's with its cause; at most the pool's connections but one at a time; each finding of a
unit's reading names its unit; a stage that cannot be set up ends its run. A model stands in."""

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.jobs.outcome import PermanentError
from app.jobs.queue import LeaseLost
from app.pipeline import asking, x4_statements
from app.pipeline.run import extract_document
from tests.llm.test_client import llm_settings
from tests.pipeline.test_run import (
    BODY,
    CV,
    Model,
    a_document,
    a_job,
    a_statement,
    block,
    context_of,
    rows,
    setup,
)
from tests.pipeline.test_x3_frame import prompt_of, x3_run
from tests.pipeline.test_x4_statements import FIELDS, units_done, with_concurrency, x4_runs
from tests.support import make_settings

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run

# "Inhaltsfeld 3" alone is longer than a small context window holds; the frame's window and the
# others' leave it out
LONG = [*FIELDS[:-1], block("p3-b4", " ".join([BODY] * 120))]


async def test_a_unit_no_window_fits_ends_the_job_before_any_unit_is_asked(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=LONG)
    model = Model()
    context = context_of(pool, tmp_path, model, database_url)
    small = llm_settings(llm_context_tokens=21_000, llm_max_output_tokens=1_000)  # some 2 700 for a prefix

    with pytest.raises(PermanentError) as ended:
        await extract_document(
            replace(context, llm=small), await a_job(connection, document.id, document.owner_id)
        )

    assert ended.value.code == "prefix_too_long"
    assert [outcome for outcome, _ in await x3_run(connection, document)] == ["done"]
    assert (model.units, await x4_runs(connection, document)) == ([], [])  # none asked, no run begun


async def test_an_error_in_one_unit_ends_those_asking_beside_it_and_nothing_of_them_is_written(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===\nE2 " in (prompt := prompt_of(messages)):
            await asyncio.sleep(1)  # E3 is answered meanwhile, and its write finds the lease lost
        elif "=== EINHEIT ===\nE3 " in prompt:
            await connection.execute(
                "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
            )
        return model(messages, info)

    context = with_concurrency(context_of(pool, tmp_path, answer, database_url), database_url, 2)
    with pytest.raises(LeaseLost):
        await extract_document(context, job)

    assert await units_done(connection, document) == []
    assert "E4" not in model.units
    assert [(outcome, result["failure"]) for outcome, result in await x4_runs(connection, document)] == [
        ("failed", "LeaseLost")
    ]


async def test_the_error_that_ended_the_units_keeps_its_cause(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)

    async def refused(*_: Any, **__: Any) -> int:
        raise RuntimeError("the write was refused") from OSError("the database went away")

    monkeypatch.setattr(x4_statements, "write_unit", refused)
    with pytest.raises(RuntimeError) as ended:
        await extract_document(
            context_of(pool, tmp_path, Model(), database_url),
            await a_job(connection, document.id, document.owner_id),
        )

    assert isinstance(ended.value.__cause__, OSError)


async def test_no_more_units_are_asked_at_once_than_the_pool_leaves_beside_the_worker(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    model = Model()
    asking_now = {"now": 0, "most": 0}

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===" in prompt_of(messages):
            asking_now["now"] += 1
            asking_now["most"] = max(asking_now["most"], asking_now["now"])
            await asyncio.sleep(0.2)
            asking_now["now"] -= 1
        return model(messages, info)

    settings = make_settings(database_url=database_url, extract_concurrency=4, db_pool_max_size=3)
    context = replace(context_of(pool, tmp_path, answer, database_url), settings=settings)
    await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert asking_now["most"] == 2


async def test_each_finding_of_a_unit_s_reading_names_its_unit(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    told = a_statement("p2-b3", "Aussage") | {"contextText": "im Labor"}  # in no block of it
    model = Model(units={"E2": {"unitKey": "E2", "statements": [told], "checkedAbsent": []}})

    await extract_document(
        context_of(pool, tmp_path, model, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert await rows(
        connection,
        "SELECT f.rule, f.details ->> 'unit' FROM validation_finding f"
        " JOIN extraction_run r ON r.id = f.run_id WHERE r.stage_iri = %s",
        CV + "stage_X4",
    ) == [("x4.value_from_surroundings", "E2")]


async def test_a_stage_whose_question_cannot_be_set_up_ends_its_run_as_failed(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    load = asking.load_schema

    def missing(directory: Any, name: str) -> Any:
        if name == "x4-aussagen":
            raise FileNotFoundError(name)
        return load(directory, name)

    monkeypatch.setattr(asking, "load_schema", missing)
    with pytest.raises(FileNotFoundError):
        await extract_document(
            context_of(pool, tmp_path, Model(), database_url),
            await a_job(connection, document.id, document.owner_id),
        )

    assert [(outcome, result["failure"]) for outcome, result in await x4_runs(connection, document)] == [
        ("failed", "FileNotFoundError")
    ]
