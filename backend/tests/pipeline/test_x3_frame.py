"""X3 in the job extract.run (plan M1 7b, 7.1; F2): the document's frame asked once behind the prefix
the units share - the whole document, its profile, no choice lists yet -, its frame parts and the
statements of its frame ranges written at once with the run's end under the lease and the
document's lock; a run done meanwhile, a budget spent or a lease lost writes nothing of it. A
model stands in (FunctionModel), never a provider."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo

from app.db.runs import RunStart, finish_run, start_run
from app.jobs.outcome import PermanentError
from app.jobs.queue import LeaseLost
from app.pipeline import run
from app.pipeline.run import extract_document
from tests.llm.test_client import llm_settings
from tests.pipeline.test_run import (
    BLOCKS,
    BODY,
    CV,
    EMPTY_FRAME,
    Model,
    a_document,
    a_job,
    block,
    context_of,
    rows,
    setup,
)

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["setup"]  # the fixture, shared with test_run

# BLOCKS of test_run: E0 the title pages (p1-b1, p1-b2), E1 and E2 the competences, E3 "Leistungsbewertung"
# (p3-b1, p3-b2), a frame part by X1's outline
STATEMENT: dict[str, Any] = {
    "blockIds": ["p3-b2"], "verbatim": "Die Leistung wird in allen Bereichen bewertet.", "leadIn": None,
    "statementKind": "mandate", "statementSubkind": None, "addressee": "educator", "obligation": None,
    "layoutMarkers": [], "codeText": None, "levelText": None, "timeText": None, "contextText": None,
    "referenceMarker": None, "exampleText": None, "purposeText": None, "crossCuttingMarkers": [],
    "targetsContent": [],
}  # fmt: skip
FRAME = EMPTY_FRAME | {
    "competencyModels": [
        {
            "title": "Kompetenzbereiche",
            "dimensions": [{"code": "K1", "label": "Kommunikation", "parentLabel": None}],
            "evidenceBlockIds": ["p2-b1", "p2-b2"],
        }
    ],
    "operators": [
        {"lemma": "erklären", "definition": None, "taskDemandText": None, "evidenceBlockId": "p2-b2"}
    ],
    "statements": [STATEMENT, STATEMENT | {"blockIds": ["p2-b4"], "verbatim": "Optik ist X4s."}],
    "checkedAbsent": ["level"],
}


def prompt_of(messages: list[ModelMessage]) -> str:
    return str(messages[0].parts[-1].content)  # type: ignore[union-attr]


async def x3_run(connection: Any, document: Any) -> list[tuple[Any, ...]]:
    return await rows(
        connection,
        "SELECT outcome, result FROM extraction_run WHERE document_id = %s AND stage_iri = %s"
        " ORDER BY started_at",
        document.id,
        CV + "stage_X3",
    )


def frame_of(asked: list[str]) -> str:
    [frame] = [prompt for prompt in asked if "=== RAHMENBEREICHE ===" in prompt]
    return frame


async def written(connection: Any, document: Any) -> tuple[Any, Any]:
    [(parts,)] = await rows(connection, "SELECT count(*) FROM frame_part WHERE document_id = %s", document.id)
    [(statements,)] = await rows(
        connection,
        "SELECT count(*) FROM statement s JOIN extraction_run r ON r.id = s.run_id"
        " WHERE s.document_id = %s AND r.stage_iri = %s",
        document.id,
        CV + "stage_X3",
    )  # X3's: X4 writes the units' after it
    return parts, statements


async def test_the_frame_is_asked_once_behind_the_prefix_and_written_with_its_anchors(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    asked: list[str] = []
    model = Model(frame=FRAME)

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        asked.append(prompt_of(messages))
        return model(messages, info)

    await extract_document(context_of(pool, tmp_path, answer, database_url), job)

    frame = frame_of(asked)
    assert frame.startswith("=== DOKUMENT ===\n")  # the whole document fits: every unit reads the same bytes
    assert "[p3-b2] Die Schülerinnen und Schüler" in frame
    assert "=== DOKUMENTPROFIL ===\nTitel: Kernlehrplan für die Sekundarstufe I Physik\n" in frame
    assert "=== AUSWAHLLISTEN ===" not in frame  # X3 makes them
    assert (
        "E0 | Titelei | Blöcke p1-b1 bis p1-b2\nE3 | Leistungsbewertung | Blöcke p3-b1 bis p3-b2\n" in frame
    )
    assert "U1: " in frame  # the school's statement subkinds, keyed, with their profile's hints:
    assert "Kompetenzerwartung (Aussageart learningOutcome) — Ergebnisorientierte" in frame
    assert "— Hinweise: Wortlaut: Wortlaut wörtlich ohne den gemeinsamen Einleitungssatz" in frame
    assert "gegliedert: bullet; Adressat meist: learner\n" in frame
    assert await rows(
        connection,
        "SELECT p.part_kind, p.content, array_agg(b.block_id ORDER BY b.block_id), r.stage_iri"
        " FROM frame_part p JOIN anchor a ON a.frame_part_id = p.id JOIN anchor_block b ON b.anchor_id = a.id"
        " JOIN extraction_run r ON r.id = p.run_id WHERE p.document_id = %s"
        " GROUP BY p.id, p.part_kind, p.content, r.stage_iri ORDER BY p.id",
        document.id,
    ) == [
        (
            "competencyModels",
            {
                "title": "Kompetenzbereiche",
                "dimensions": [{"code": "K1", "label": "Kommunikation", "parentLabel": None}],
            },
            ["p2-b1", "p2-b2"],
            CV + "stage_X3",
        ),
        (
            "operators",
            {"lemma": "erklären", "definition": None, "taskDemandText": None},
            ["p2-b2"],
            CV + "stage_X3",
        ),
    ]
    assert await rows(
        connection,
        "SELECT n.original_title, s.position, s.verbatim, replace(s.origin_iri, %s, ''),"
        " replace(s.review_status_iri, %s, '') FROM statement s JOIN node n ON n.id = s.node_id"
        " JOIN extraction_run r ON r.id = s.run_id WHERE s.document_id = %s AND r.stage_iri = %s",
        CV,
        CV,
        document.id,
        CV + "stage_X3",
    ) == [
        (
            "Leistungsbewertung",
            1,
            "Die Leistung wird in allen Bereichen bewertet.",
            "orig_model",
            "rev_proposed",
        )
    ]
    assert await x3_run(connection, document) == [
        (
            "done",
            {"parts": {"competencyModels": 1, "operators": 1}, "statements": 1, "checkedAbsent": ["level"]},
        )
    ]
    assert await rows(
        connection,
        "SELECT f.rule FROM validation_finding f JOIN extraction_run r ON r.id = f.run_id"
        " WHERE r.stage_iri = %s",
        CV + "stage_X3",
    ) == [("x3.statement_outside_frame",)]


async def test_a_run_of_x3_done_while_this_one_asked_is_found_at_the_write(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model(frame=FRAME)

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== RAHMENBEREICHE ===" in prompt_of(messages):  # another job's run of X3 ends first
            other = RunStart(document.id, None, None, "X3", None, None, None, None)
            await finish_run(connection, await start_run(connection, other), "done", {})
        return model(messages, info)

    result = await extract_document(context_of(pool, tmp_path, answer, database_url), job)

    assert result["stages"] == ["X1", "X2", "X3", "X4"]
    assert [(outcome, result.get("failure")) for outcome, result in await x3_run(connection, document)] == [
        ("failed", "X3 of the document was written by another run meanwhile"),  # this one's, begun first
        ("done", None),
    ]
    assert await written(connection, document) == (0, 0)


async def test_a_budget_spent_before_the_frame_is_asked_keeps_x1_and_x2_and_a_new_job_asks_the_frame_alone(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # spent while X1's last question is asked (another job of the account): X3's one request is refused
    pool, connection = setup
    document = await a_document(connection)
    model = Model(frame=FRAME)

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if prompt_of(messages).startswith("=== KNOTENTYPEN"):  # the outline's
            await connection.execute(
                "UPDATE quota SET token_limit = 2000 WHERE account_id = %s", (document.owner_id,)
            )
        return model(messages, info)

    context = context_of(pool, tmp_path, answer, database_url)
    with pytest.raises(PermanentError) as ended:
        await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert ended.value.code == "budget_exhausted"
    assert [outcome for outcome, _ in await x3_run(connection, document)] == ["budget_exhausted"]
    assert await written(connection, document) == (0, 0)

    await connection.execute(
        "UPDATE quota SET token_limit = NULL WHERE account_id = %s", (document.owner_id,)
    )
    await extract_document(context, await a_job(connection, document.id, document.owner_id))

    assert model.asked == ["profile", "outline", "frame"]  # the refused request never reached it
    assert await written(connection, document) == (2, 1)


async def test_an_attempt_that_lost_its_lease_while_the_frame_was_asked_writes_nothing(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model(frame=FRAME)

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "=== RAHMENBEREICHE ===" in prompt_of(messages):
            await connection.execute(
                "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
            )
        return model(messages, info)

    with pytest.raises(LeaseLost):
        await extract_document(context_of(pool, tmp_path, answer, database_url), job)

    assert [(outcome, result["failure"]) for outcome, result in await x3_run(connection, document)] == [
        ("failed", "LeaseLost")
    ]
    assert await written(connection, document) == (0, 0)


async def test_a_document_no_window_of_which_fits_the_model_ends_the_job(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    context = context_of(pool, tmp_path, Model(), database_url)
    small = llm_settings(llm_context_tokens=8_000)  # less than a request's rest and its answer's cap

    with pytest.raises(PermanentError) as ended:
        await extract_document(
            replace(context, llm=small),
            await a_job(connection, document.id, document.owner_id),
        )

    assert ended.value.code == "prefix_too_long"
    assert await x3_run(connection, document) == []  # no run began


async def test_a_job_that_finds_x3_done_since_it_looked_asks_nothing_of_it(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    model = Model(frame=FRAME)
    context = context_of(pool, tmp_path, model, database_url)
    await extract_document(context, await a_job(connection, document.id, document.owner_id))
    later = await a_job(connection, document.id, document.owner_id)

    async def as_read_before(*_: Any) -> set[str]:
        return {"X1", "X2"}  # the look before the other job's commit of X3

    monkeypatch.setattr(run, "done_stages", as_read_before)
    await extract_document(context, later)

    assert model.asked == ["profile", "outline", "frame"]  # the other job's alone
    assert await rows(connection, "SELECT count(*) FROM extraction_run WHERE job_id = %s", later.id) == [(0,)]
    assert await written(connection, document) == (2, 1)


async def test_the_lexicon_excerpt_holds_the_cues_of_the_type_x1_read_that_bear_on_the_frame(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # "Regelstandard" is a cue of the Bildungsstandards alone (school#cue-ke-regelstandard): X1 read a
    # Lehrplan, and X3 reads the document as X1 left it
    pool, connection = setup
    blocks = [*BLOCKS[:-1], block("p3-b2", BODY + " Der Regelstandard gilt.")]
    document = await a_document(connection, blocks=blocks)
    asked: list[str] = []
    model = Model(frame=FRAME)

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        asked.append(prompt_of(messages))
        return model(messages, info)

    await extract_document(
        context_of(pool, tmp_path, answer, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    lexicon = frame_of(asked).split("=== LEXIKON ===\n", 1)[1].split("=== AUFTRAG ===", 1)[0]
    assert (
        "Satzmuster /^(Die )?(Schülerinnen und Schüler|Lernenden|SuS)\\b/ → Kompetenzerwartung (U" in lexicon
    )
    assert "Regelstandard" not in lexicon
