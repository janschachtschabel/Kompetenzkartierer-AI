"""X4 in the job extract.run (plan M1 7b, 7.2, 7.3; F3, F4, F11, F12): each unit asked once behind the
prefix every unit shares - the document, its profile, X3's choice lists with the profile's subkinds -,
at most EXTRACT_CONCURRENCY at a time, each written whole on its own; a unit answered for another stays
open for the next job; a lease lost ends them all. A model stands in (FunctionModel), never a provider."""

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.db.runs import RunStart, finish_run, start_run
from app.db.units import mark_unit
from app.jobs.outcome import PermanentError
from app.jobs.queue import LeaseLost
from app.pipeline import x4_question
from app.pipeline.lexicon_excerpt import Excerpt
from app.pipeline.run import extract_document
from tests.db.document_of import document_of
from tests.pipeline.test_run import BODY, CV, PLAIN, Model, a_document, a_job, block, context_of, rows, setup
from tests.pipeline.test_x3_frame import FRAME, prompt_of
from tests.support import make_settings

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run

# three units of statements: the headings typed by NW's pattern ("Inhaltsfeld …"), never asked;
# "Kompetenzen" holds its heading alone and asks for nothing
FIELDS = [
    block("p1-b1", "Kernlehrplan für die Sekundarstufe I Physik", size=24),
    block("p2-b1", "Kompetenzen", size=16),
    block("p2-b2", "Inhaltsfeld 1: Optik", size=13),
    block("p2-b3", BODY),
    block("p3-b1", "Inhaltsfeld 2: Mechanik", size=13),
    block("p3-b2", BODY),
    block("p3-b3", "Inhaltsfeld 3: Wärme", size=13),
    block("p3-b4", BODY),
]


def with_concurrency(context: Any, database_url: str, units: int) -> Any:
    return replace(context, settings=make_settings(database_url=database_url, extract_concurrency=units))


async def x4_runs(connection: Any, document: Any) -> list[tuple[Any, ...]]:
    return await rows(
        connection,
        "SELECT outcome, result FROM extraction_run WHERE document_id = %s AND stage_iri = %s"
        " ORDER BY started_at",
        document.id,
        CV + "stage_X4",
    )


async def units_done(connection: Any, document: Any) -> list[tuple[Any, ...]]:
    return await rows(
        connection,
        "SELECT u.unit_key, u.statements, r.stage_iri FROM extraction_unit u"
        " JOIN extraction_run r ON r.id = u.run_id WHERE u.document_id = %s ORDER BY u.unit_key",
        document.id,
    )


async def test_each_unit_is_asked_once_behind_the_prefix_they_share_and_written(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model(frame=FRAME)
    prompts: dict[str, str] = {}

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        response = model(messages, info)
        if "=== EINHEIT ===" in (prompt := prompt_of(messages)):
            prompts[model.units[-1]] = prompt
        return response

    result = await extract_document(context_of(pool, tmp_path, answer, database_url), job)

    assert result["stages"] == ["X1", "X2", "X3", "X4"]
    assert sorted(model.units) == ["E1", "E2"]
    shared = {key: prompt.split("=== EINHEIT ===")[0] for key, prompt in prompts.items()}
    assert shared["E1"] == shared["E2"]  # the same bytes: one cache for every unit
    assert (
        "=== AUSWAHLLISTEN ===\nKompetenzmodelle:\n- Kompetenzbereiche: K1 Kommunikation\n"
        "Operatoren: erklären\nAussage-Unterarten (statementSubkind):\nU1: "
    ) in shared["E1"]
    assert (
        "E2 | Kompetenzen / Inhaltsfeld 1: Optik | Blöcke p2-b3 bis p2-b4\nKnotentyp: Inhaltsbereich — "
        in (prompts["E2"])
    )
    assert (
        "Gib die Aussagen der Einheit E1 zurück, die in den Blöcken p2-b1 bis p2-b2 stehen" in prompts["E1"]
    )
    assert await rows(
        connection,
        "SELECT n.original_title, s.position, s.verbatim, replace(s.origin_iri, %s, ''), r.stage_iri"
        " FROM statement s JOIN node n ON n.id = s.node_id JOIN extraction_run r ON r.id = s.run_id"
        " WHERE s.document_id = %s AND r.stage_iri = %s ORDER BY s.verbatim",
        CV,
        document.id,
        CV + "stage_X4",
    ) == [
        ("Kompetenzen", 1, "Aussage E1", "orig_model", CV + "stage_X4"),
        ("Inhaltsfeld 1: Optik", 1, "Aussage E2", "orig_model", CV + "stage_X4"),
    ]
    assert await units_done(connection, document) == [("E1", 1, CV + "stage_X4"), ("E2", 1, CV + "stage_X4")]
    assert await x4_runs(connection, document) == [("done", {"units": 2, "statements": 2, "taken": 0})]
    assert await rows(
        connection, "SELECT sum(requests) FROM llm_usage WHERE job_id = %s AND purpose = 'x4.unit'", job.id
    ) == [(2,)]
    [(progress,)] = await rows(connection, "SELECT progress FROM job WHERE id = %s", job.id)
    assert progress == {"code": "extract_statements", "params": {"done": 2, "total": 2}}


@pytest.mark.parametrize("concurrency", [1, 2])
async def test_at_most_extract_concurrency_units_are_asked_at_once(
    setup: Any, tmp_path: Path, database_url: str, concurrency: int
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    model = Model()
    asking = {"now": 0, "most": 0}

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        unit = "=== EINHEIT ===" in prompt_of(messages)
        if unit:
            asking["now"] += 1
            asking["most"] = max(asking["most"], asking["now"])
            await asyncio.sleep(0.2)  # the others begin meanwhile, as far as they may
            asking["now"] -= 1
        return model(messages, info)

    context = with_concurrency(context_of(pool, tmp_path, answer, database_url), database_url, concurrency)
    await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert asking["most"] == concurrency
    assert sorted(model.units) == ["E2", "E3", "E4"]  # E1 is "Kompetenzen", its heading alone
    assert [key for key, _, _ in await units_done(connection, document)] == ["E2", "E3", "E4"]


async def test_a_unit_answered_for_another_stays_open_and_a_new_job_asks_it_alone(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    model = Model(units={"E3": {"unitKey": "E9", "statements": [], "checkedAbsent": []}})
    context = context_of(pool, tmp_path, model, database_url)

    with pytest.raises(PermanentError) as ended:
        await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert ended.value.code == "model_unanswered"
    assert [key for key, _, _ in await units_done(connection, document)] == ["E2", "E4"]
    assert [outcome for outcome, _ in await x4_runs(connection, document)] == ["failed"]
    assert await rows(
        connection,
        "SELECT f.rule, f.details FROM validation_finding f JOIN extraction_run r ON r.id = f.run_id"
        " WHERE r.stage_iri = %s",
        CV + "stage_X4",
    ) == [("x4.unanswered", {"units": ["E3"]})]

    model.answers = {}
    await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert sorted(model.units) == ["E2", "E3", "E3", "E4"]
    assert [key for key, _, _ in await units_done(connection, document)] == ["E2", "E3", "E4"]
    assert [outcome for outcome, _ in await x4_runs(connection, document)] == ["failed", "done"]


async def test_a_lease_lost_while_a_unit_is_asked_ends_the_units_and_writes_none_of_it(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===" in prompt_of(messages):
            await connection.execute(
                "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
            )
        return model(messages, info)

    context = with_concurrency(context_of(pool, tmp_path, answer, database_url), database_url, 1)
    with pytest.raises(LeaseLost):
        await extract_document(context, job)

    assert model.units == ["E2"]  # the next one was never asked
    assert await units_done(connection, document) == []
    assert [(outcome, result["failure"]) for outcome, result in await x4_runs(connection, document)] == [
        ("failed", "LeaseLost")
    ]


async def test_the_one_unit_of_a_document_without_headings_gets_a_node_of_its_own(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=PLAIN)
    model = Model(specifications=False)

    await extract_document(
        context_of(pool, tmp_path, model, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert model.units == ["E1"]
    assert await rows(
        connection,
        "SELECT n.original_title, n.rule_id, s.verbatim FROM statement s JOIN node n ON n.id = s.node_id"
        " WHERE s.document_id = %s",
        document.id,
    ) == [("Kernlehrplan für die Sekundarstufe I Physik", "x4.unit_without_node", "Aussage E1")]


async def test_the_parts_of_a_node_parted_at_pages_keep_their_order_at_it(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # "Inhaltsfeld 1" runs over 17 pages: X2 parts it after 15 (MOST_PAGES), X4 asks each part
    pool, connection = setup
    blocks = [block("p1-b1", "Kernlehrplan Physik", size=24), block("p2-b1", "Inhaltsfeld 1: Optik", size=13)]
    blocks += [block(f"p{page}-b2", BODY) for page in range(2, 19)]
    document = await document_of(connection, blocks, regions=("DE-NW",))
    await connection.execute(
        "INSERT INTO quota (account_id, token_limit) VALUES (%s, NULL)", (document.owner_id,)
    )
    model = Model()

    await extract_document(
        context_of(pool, tmp_path, model, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert sorted(model.units) == ["E1", "E2"]
    assert await rows(
        connection,
        "SELECT position, verbatim FROM statement WHERE document_id = %s ORDER BY position",
        document.id,
    ) == [(1, "Aussage E1"), (10_001, "Aussage E2")]


async def test_a_unit_another_writer_did_meanwhile_counts_as_done(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, blocks=FIELDS)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        response = model(messages, info)
        if "=== EINHEIT ===" in prompt_of(messages) and model.units[-1] == "E3":
            [(run,)] = await rows(
                connection,
                "SELECT id FROM extraction_run WHERE document_id = %s AND outcome IS NULL",
                document.id,
            )  # this one's: the other writer's run is as good
            await mark_unit(
                connection, document.id, "E3", run_id=run, node_id=None, statements=0, checked_absent=[]
            )
        return response

    await extract_document(
        context_of(pool, tmp_path, answer, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert await x4_runs(connection, document) == [("done", {"units": 3, "statements": 2, "taken": 1})]
    assert await rows(
        connection,
        "SELECT count(*) FROM statement WHERE document_id = %s AND verbatim = 'Aussage E3'",
        document.id,
    ) == [(0,)]


async def test_a_run_of_x4_done_while_this_one_asked_passes_the_stage_over(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    model = Model()
    ended: list[bool] = []  # once: the units are asked side by side

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== EINHEIT ===" in prompt_of(messages) and not ended:  # another job's run of X4 ends first
            ended.append(True)
            other = RunStart(document.id, None, None, "X4", None, None, None, None)
            await finish_run(connection, await start_run(connection, other), "done", {})
        return model(messages, info)

    result = await extract_document(
        context_of(pool, tmp_path, answer, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert result["stages"] == ["X1", "X2", "X3", "X4"]
    assert [(outcome, result.get("failure")) for outcome, result in await x4_runs(connection, document)] == [
        ("failed", "X4 of the document was written by another run meanwhile"),  # this one's, begun first
        ("done", None),
    ]


async def test_a_pattern_of_the_lexicon_that_took_too_long_is_a_finding_of_its_unit(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)

    def slow(*_: Any) -> Excerpt:
        return Excerpt("", frozenset({"https://example.org/cue#slow"}))

    monkeypatch.setattr(x4_question, "lexicon_excerpt", slow)
    await extract_document(
        context_of(pool, tmp_path, Model(), database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert sorted(
        details["unit"]
        for rule, details in await rows(
            connection,
            "SELECT f.rule, f.details FROM validation_finding f JOIN extraction_run r ON r.id = f.run_id"
            " WHERE r.stage_iri = %s",
            CV + "stage_X4",
        )
        if rule == "x4.pattern_timeout"
    ) == ["E1", "E2"]
