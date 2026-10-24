"""The job extract.run (plan M1 6.6): X1 and X2 of a document one after the other, each stage of each
attempt a run of its own, written at once with its run's end under the attempt's lease; an attempt
after a break goes on from the last stage done; a spent budget ends the job and keeps what is done.
A model stands in (FunctionModel), never a provider."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from app.conversion.base import Block
from app.core.storage import FileSystemStorage
from app.core.storage_async import AsyncStorage
from app.db.documents import Document, set_document_type
from app.db.migrate import migrate
from app.db.nodes import write_subtree
from app.domain.l1 import NodeDraft
from app.jobs.context import JobContext
from app.jobs.handlers import make_handlers
from app.jobs.outcome import PermanentError
from app.jobs.queue import Job, LeaseLost, account_lane, claim, enqueue
from app.pipeline import run, x1_stage
from app.pipeline.run import KIND, extract_document
from app.usage.admission import MODEL_JOB_KINDS
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of
from tests.llm.test_client import llm_settings
from tests.support import make_settings

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
VOCATIONAL = "https://w3id.org/wlo/curriculum/profile/vocational#"
BODY = "Die Schülerinnen und Schüler beschreiben, wie Licht sich ausbreitet, und erklären Schatten."


def block(block_id: str, words: str, size: float = 10) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id,
        page=page,
        kind="text",
        text=words,
        bbox=(0, 0, 1, 1),
        font_size=size,
        bold=False,
        italic=False,
    )


BLOCKS = [
    block("p1-b1", "Kernlehrplan für die Sekundarstufe I Physik", size=24),
    block("p1-b2", "Dieser Kernlehrplan tritt am 1. August 2019 in Kraft."),
    block("p2-b1", "Kompetenzen", size=16),
    block("p2-b2", BODY),
    block("p2-b3", "Inhaltsfeld 1: Optik", size=13),  # typed by NW's pattern, never asked
    block("p2-b4", BODY),
    block("p3-b1", "Leistungsbewertung", size=16),
    block("p3-b2", BODY),
]


class Model:
    """The model of both X1 questions: it answers each by the keys its prompt lists."""

    def __init__(
        self,
        *,
        profile_out_of_form: bool = False,
        specifications: bool = True,
        document_type: str = "Lehrplan",
    ) -> None:
        self.asked: list[str] = []
        self.profile_out_of_form = profile_out_of_form
        self.specifications = specifications
        self.document_type = document_type  # the label of the type it reads

    def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = str(messages[0].parts[-1].content)  # type: ignore[union-attr]
        # the output tool is pydantic-ai's own (final_result) for either schema: the prompt tells them apart
        question = "profile" if prompt.startswith("=== AUSZUG AUS DEM DOKUMENT ===") else "outline"
        self.asked.append(question)
        answer = self.profile(prompt) if question == "profile" else self.outline(prompt)
        usage = RequestUsage(input_tokens=1_000, output_tokens=100)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, json.dumps(answer))], usage=usage)

    def profile(self, prompt: str) -> dict[str, Any]:
        if self.profile_out_of_form:
            return {"document": {}}
        lehrplan = re.search(rf"^(D\d+): {re.escape(self.document_type)}\b", prompt, re.M)
        assert lehrplan is not None
        return {
            "document": {
                "title": "Kernlehrplan für die Sekundarstufe I Physik",
                "documentType": lehrplan[1],
                "legalForm": "administrativeRegulation",
                "documentBinding": "binding",
                "lifecycle": "inForce",
                "educationSectors": ["school"],
                "regions": ["DE-NW"],
                "issuerText": None,
                "issuedText": None,
                "validFromText": "1. August 2019",
                "editionText": None,
                "evidenceBlockIds": ["p1-b1", "p1-b2"],
            },
            "specifications": [
                {
                    "key": "S1",
                    "kind": "curriculum",
                    "title": "Physik",
                    "fieldText": "Physik",
                    "applicability": {
                        "sector": "school", "formality": "formal", "timeKind": None, "timeText": None,
                        "levelText": None, "institutionText": None, "targetGroupText": None,
                        "evidenceBlockIds": [],
                    },
                    "variants": [],
                }
            ] if self.specifications else [],
            "termMappings": [],
            "newTerms": [],
        }  # fmt: skip

    def outline(self, prompt: str) -> dict[str, Any]:
        area = re.search(r"^(T\d+): Kompetenzbereich\b", prompt, re.M)
        asked = re.findall(r"^(H\d+) \| ", prompt, re.M)
        return {
            "headings": [
                {
                    "headingId": key,
                    "nodeType": area[1] if area is not None and key == "H1" else None,
                    "nodeFunction": "area" if key == "H1" else "frame",
                    "appliesTo": [],
                    "scopeShare": None,
                }
                for key in asked
            ]
        }


@pytest.fixture
async def setup(
    database_url: str, tmp_path: Path
) -> AsyncIterator[tuple[AsyncConnectionPool, psycopg.AsyncConnection]]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with (
        AsyncConnectionPool(database_url, min_size=1, max_size=6, open=False) as pool,
        await psycopg.AsyncConnection.connect(database_url, autocommit=True) as connection,
    ):
        yield pool, connection


def context_of(pool: AsyncConnectionPool, tmp_path: Path, model: Any, database_url: str) -> JobContext:
    function_model = None if model is None else FunctionModel(model, settings={"max_tokens": 4_000})
    return JobContext(
        pool=pool,
        storage=AsyncStorage(FileSystemStorage(tmp_path / "store")),
        settings=make_settings(database_url=database_url),
        llm=llm_settings(),
        model=None if function_model is None else (lambda: function_model),
    )


# a document of no headings, whose profile names no specification: X1 writes no row X1 is told by
PLAIN = [
    block("p1-b1", "Kernlehrplan Physik"),
    block("p1-b2", BODY),
    block("p2-b1", BODY),
    block("p3-b1", BODY),
]


async def a_document(
    connection: psycopg.AsyncConnection, *, token_limit: int | None = None, blocks: list[Block] = BLOCKS
) -> Document:
    document = await document_of(connection, blocks, regions=("DE-NW",), printed_pages=[None, "1", "2"])
    await connection.execute(
        "INSERT INTO quota (account_id, token_limit) VALUES (%s, %s)", (document.owner_id, token_limit)
    )
    return document


async def a_job(connection: psycopg.AsyncConnection, document_id: UUID | str, owner: UUID) -> Job:
    await enqueue(connection, KIND, account_lane(owner), {"document_id": str(document_id)})
    job = await claim(connection, "w1", [KIND], 60)
    assert job is not None
    return job


async def rows(connection: psycopg.AsyncConnection, query: str, *params: Any) -> list[tuple[Any, ...]]:
    cursor = await connection.execute(query, params)
    return await cursor.fetchall()


async def test_a_document_is_extracted_stage_by_stage_each_a_run(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    model = Model()
    job = await a_job(connection, document.id, document.owner_id)

    result = await extract_document(context_of(pool, tmp_path, model, database_url), job)

    assert result == {"document_id": str(document.id), "stages": ["X1", "X2"], "packages": 4}
    assert model.asked == ["profile", "outline"]
    assert await rows(
        connection,
        "SELECT replace(stage_iri, %s, ''), attempt, outcome, model FROM extraction_run WHERE job_id = %s"
        " ORDER BY started_at",
        CV + "stage_",
        job.id,
    ) == [("X1", 1, "done", "gpt-6-luna"), ("X2", 1, "done", None)]
    [(title, document_type, valid_from)] = await rows(
        connection, "SELECT title, document_type_iri, valid_from FROM document WHERE id = %s", document.id
    )
    assert (title, document_type, valid_from) == (
        "Kernlehrplan für die Sekundarstufe I Physik", SCHOOL + "dt-Lehrplan", "2019-08-01",
    )  # fmt: skip
    nodes = await rows(
        connection,
        "SELECT original_title, replace(origin_iri, %s, ''), node_type_iri FROM node WHERE document_id = %s"
        " ORDER BY original_title",
        CV,
        document.id,
    )
    assert nodes == [
        ("Inhaltsfeld 1: Optik", "orig_rule", SCHOOL + "Inhaltsbereich"),
        ("Kompetenzen", "orig_model", SCHOOL + "Kompetenzbereich"),
        ("Leistungsbewertung", "orig_model", None),
    ]
    [(packages,)] = await rows(
        connection,
        "SELECT result -> 'packages' FROM extraction_run WHERE job_id = %s AND stage_iri = %s",
        job.id,
        CV + "stage_X2",
    )
    assert [(item["key"], item["job"]) for item in packages] == [
        ("E0", "frame"), ("E1", "statements"), ("E2", "statements"), ("E3", "frame"),
    ]  # fmt: skip
    [(progress,)] = await rows(connection, "SELECT progress FROM job WHERE id = %s", job.id)
    assert progress == {"code": "extract_segments", "params": {"units": 4}}
    spent = await rows(
        connection,
        "SELECT purpose, sum(requests) FROM llm_usage WHERE job_id = %s GROUP BY purpose ORDER BY purpose",
        job.id,
    )
    assert spent == [("x1.outline", 1), ("x1.profile", 1)]
    kept = sorted(path.name for path in (tmp_path / "store").rglob("*.json"))
    assert kept == ["1.json", "2.json"]  # both answers as they came, under the X1 run


async def test_an_attempt_after_a_break_goes_on_from_the_last_stage_done(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    model = Model()
    job = await a_job(connection, document.id, document.owner_id)
    context = context_of(pool, tmp_path, model, database_url)

    async def broken(*_: Any) -> Any:
        raise RuntimeError("the worker died")

    with monkeypatch.context() as patched:
        patched.setattr(run, "work_packages", broken)
        with pytest.raises(RuntimeError):
            await extract_document(context, job)
    again = await extract_document(context, job)

    assert again["stages"] == ["X1", "X2"]
    assert model.asked == ["profile", "outline"]  # X1 was done: not asked again
    assert await rows(
        connection,
        "SELECT replace(stage_iri, %s, ''), outcome FROM extraction_run WHERE job_id = %s"
        " ORDER BY started_at",
        CV + "stage_",
        job.id,
    ) == [("X1", "done"), ("X2", "done")]  # the broken attempt started no run of X2
    [(nodes,)] = await rows(connection, "SELECT count(*) FROM node WHERE document_id = %s", document.id)
    assert nodes == 3  # written once


async def test_a_stage_that_breaks_ends_its_run_and_is_asked_again(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)

    async def refused(*_: Any) -> Any:
        raise RuntimeError("the database refused the write")

    monkeypatch.setattr(x1_stage, "write_profile", refused)
    with pytest.raises(RuntimeError):
        await extract_document(context_of(pool, tmp_path, Model(), database_url), job)

    assert await rows(connection, "SELECT outcome, result ->> 'failure' FROM extraction_run") == [
        ("failed", "RuntimeError")
    ]


async def test_the_headings_are_read_by_the_type_the_editors_set_not_by_x1_s(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # "CE 01" is a Curriculare Einheit in a Pflege-Rahmenplan alone (vocational#c-ce-1)
    pool, connection = setup
    blocks = [
        block("p1-b1", "Rahmenplan der Fachkommission", size=24),
        block("p2-b1", "CE 01 Ausbildungsstart", size=16),
        block("p2-b2", BODY),
        block("p3-b1", BODY),
    ]
    document = await document_of(connection, blocks, sector="vocational", regions=())
    await connection.execute(
        "INSERT INTO quota (account_id, token_limit) VALUES (%s, NULL)", (document.owner_id,)
    )
    await set_document_type(connection, document.id, VOCATIONAL + "dt-PflegeRahmenplan")
    model = Model(document_type="Ausbildungsordnung")  # X1 reads it otherwise

    await extract_document(
        context_of(pool, tmp_path, model, database_url),
        await a_job(connection, document.id, document.owner_id),
    )

    assert await rows(
        connection,
        "SELECT node_type_iri, replace(origin_iri, %s, '') FROM node WHERE document_id = %s",
        CV,
        document.id,
    ) == [(VOCATIONAL + "CurriculareEinheit", "orig_rule")]
    assert model.asked == ["profile"]  # typed by its pattern: nothing left to ask
    assert await rows(connection, "SELECT document_type_iri FROM document WHERE id = %s", document.id) == [
        (VOCATIONAL + "dt-PflegeRahmenplan",)
    ]


async def test_a_spent_budget_ends_the_job_and_writes_nothing_of_the_stage(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection, token_limit=100)  # less than the profile's first request
    job = await a_job(connection, document.id, document.owner_id)

    with pytest.raises(PermanentError) as ended:
        await extract_document(context_of(pool, tmp_path, Model(), database_url), job)

    assert ended.value.code == "budget_exhausted"
    assert await rows(connection, "SELECT outcome FROM extraction_run WHERE job_id = %s", job.id) == [
        ("budget_exhausted",)
    ]
    assert await rows(connection, "SELECT title FROM document WHERE id = %s", document.id) == [(None,)]


def is_profile(messages: list[ModelMessage]) -> bool:
    return str(messages[0].parts[-1].content).startswith("=== AUSZUG")  # type: ignore[union-attr]


async def test_a_budget_spent_before_the_outline_is_asked_writes_nothing_of_the_stage(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # another job of the account spends it while the profile is asked: the profile is not written alone
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_profile(messages):
            await connection.execute(
                "UPDATE quota SET token_limit = 2000 WHERE account_id = %s", (document.owner_id,)
            )
        return model(messages, info)

    with pytest.raises(PermanentError) as ended:
        await extract_document(context_of(pool, tmp_path, answer, database_url), job)

    assert ended.value.code == "budget_exhausted"
    assert model.asked == ["profile"]
    assert await rows(connection, "SELECT outcome FROM extraction_run WHERE job_id = %s", job.id) == [
        ("budget_exhausted",)
    ]
    assert await rows(connection, "SELECT title FROM document WHERE id = %s", document.id) == [(None,)]
    assert await rows(connection, "SELECT count(*) FROM node WHERE document_id = %s", document.id) == [(0,)]
    assert await rows(connection, "SELECT purpose FROM llm_usage WHERE job_id = %s", job.id) == [
        ("x1.profile",)  # what was asked is charged
    ]


async def test_an_attempt_that_lost_its_lease_while_it_asked_writes_nothing(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # the lease runs out while the outline is asked: the job is another worker's by the write
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not is_profile(messages):
            await connection.execute(
                "UPDATE job SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (job.id,)
            )
        return model(messages, info)

    with pytest.raises(LeaseLost):
        await extract_document(context_of(pool, tmp_path, answer, database_url), job)

    assert model.asked == ["profile", "outline"]
    assert await rows(
        connection, "SELECT outcome, result ->> 'failure' FROM extraction_run WHERE job_id = %s", job.id
    ) == [("failed", "LeaseLost")]
    assert await rows(connection, "SELECT title FROM document WHERE id = %s", document.id) == [(None,)]
    assert await rows(connection, "SELECT count(*) FROM node WHERE document_id = %s", document.id) == [(0,)]


async def test_an_answer_never_in_form_fails_the_stage(setup: Any, tmp_path: Path, database_url: str) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)

    with pytest.raises(PermanentError) as ended:
        await extract_document(context_of(pool, tmp_path, Model(profile_out_of_form=True), database_url), job)

    assert ended.value.code == "model_unanswered"
    assert await rows(connection, "SELECT outcome FROM extraction_run WHERE job_id = %s", job.id) == [
        ("failed",)
    ]


async def test_a_job_without_a_model_or_a_document_ends_at_once(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    missing = await a_job(connection, "not-an-id", document.owner_id)
    unmodelled = await a_job(connection, document.id, document.owner_id)

    with pytest.raises(PermanentError) as gone:
        await extract_document(context_of(pool, tmp_path, Model(), database_url), missing)
    with pytest.raises(PermanentError) as no_model:
        await extract_document(context_of(pool, tmp_path, None, database_url), unmodelled)

    assert (gone.value.code, no_model.value.code) == ("document_gone", "model_not_configured")
    assert await rows(connection, "SELECT count(*) FROM extraction_run") == [(0,)]


async def test_a_document_done_before_is_neither_asked_nor_written_again(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    # a document without headings and specifications too: its X1 run says it is done
    pool, connection = setup
    document = await a_document(connection)
    model = Model()
    context = context_of(pool, tmp_path, model, database_url)
    await extract_document(context, await a_job(connection, document.id, document.owner_id))
    again = await a_job(connection, document.id, document.owner_id)

    result = await extract_document(context, again)

    assert model.asked == ["profile", "outline"]
    assert result == {"document_id": str(document.id), "stages": ["X1", "X2"], "packages": 4}
    assert await rows(connection, "SELECT count(*) FROM extraction_run WHERE job_id = %s", again.id) == [(0,)]


async def test_a_new_job_goes_on_where_one_that_failed_stopped(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a job that ends for good after X1 (attempts spent, a budget spent in a later stage)
    pool, connection = setup
    document = await a_document(connection)
    model = Model()
    context = context_of(pool, tmp_path, model, database_url)

    async def broken(*_: Any) -> Any:
        raise RuntimeError("the database went away")

    with monkeypatch.context() as patched:
        patched.setattr(run, "work_packages", broken)
        with pytest.raises(RuntimeError):
            await extract_document(context, await a_job(connection, document.id, document.owner_id))
    later = await a_job(connection, document.id, document.owner_id)

    result = await extract_document(context, later)

    assert result["packages"] == 4
    assert model.asked == ["profile", "outline"]  # X1 is not asked again
    assert await rows(
        connection,
        "SELECT replace(stage_iri, %s, ''), outcome FROM extraction_run WHERE job_id = %s",
        CV + "stage_",
        later.id,
    ) == [("X2", "done")]


@pytest.mark.parametrize(
    ("blocks", "specifications", "packages", "nodes"),
    [(BLOCKS, True, 4, 3), (PLAIN, False, 1, 0)],
    ids=["tree", "plain"],
)
async def test_two_jobs_on_one_document_write_it_once(
    setup: Any,
    tmp_path: Path,
    database_url: str,
    blocks: list[Block],
    specifications: bool,
    packages: int,
    nodes: int,
) -> None:
    # both pass the first look before either writes: the write looks again under the document's lock
    pool, connection = setup
    document = await a_document(connection, blocks=blocks)
    model = Model(specifications=specifications)
    both_asked = asyncio.Barrier(2)

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_profile(messages):
            await both_asked.wait()
        return model(messages, info)

    context = context_of(pool, tmp_path, answer, database_url)
    first = await a_job(connection, document.id, document.owner_id)
    second = await a_job(connection, document.id, document.owner_id)

    results = await asyncio.gather(extract_document(context, first), extract_document(context, second))

    assert [result["packages"] for result in results] == [packages, packages]
    assert await rows(connection, "SELECT count(*) FROM node WHERE document_id = %s", document.id) == [
        (nodes,)
    ]
    anchors = (
        "SELECT count(*) FROM anchor WHERE document_id = %s AND node_id IS NULL AND specification_id IS NULL"
    )
    assert await rows(connection, anchors, document.id) == [(1,)]  # the document's own, once
    outcomes = await rows(
        connection,
        "SELECT outcome, result ->> 'failure' FROM extraction_run WHERE document_id = %s AND stage_iri = %s"
        " ORDER BY outcome",
        document.id,
        CV + "stage_X1",
    )
    assert outcomes == [("done", None), ("failed", "X1 of the document was written by another run meanwhile")]


def by_hand() -> NodeDraft:
    """A root the editors set up."""
    return NodeDraft(function=CV + "fn_area", origin=CV + "orig_human", review_status=CV + "rev_proposed")


async def test_a_document_with_a_tree_no_extraction_wrote_is_not_extracted(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    await write_subtree(connection, document.id, by_hand())

    with pytest.raises(PermanentError) as ended:
        await extract_document(
            context_of(pool, tmp_path, Model(), database_url),
            await a_job(connection, document.id, document.owner_id),
        )

    assert ended.value.code == "document_has_tree"


async def test_a_job_that_finds_x1_written_since_it_looked_goes_on_with_x2(
    setup: Any, tmp_path: Path, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # another job wrote X1 between this one's look at the stages done and its start of X1
    pool, connection = setup
    document = await a_document(connection)
    model = Model()
    context = context_of(pool, tmp_path, model, database_url)
    await extract_document(context, await a_job(connection, document.id, document.owner_id))
    later = await a_job(connection, document.id, document.owner_id)

    async def as_read_before(*_: Any) -> set[str]:
        return set()  # the look before the other job's commit

    monkeypatch.setattr(run, "done_stages", as_read_before)
    result = await extract_document(context, later)

    assert result["packages"] == 4
    assert model.asked == ["profile", "outline"]  # the other job's alone
    assert await rows(
        connection,
        "SELECT replace(stage_iri, %s, '') FROM extraction_run WHERE job_id = %s",
        CV + "stage_",
        later.id,
    ) == [("X2",)]


async def test_a_tree_set_up_by_hand_while_x1_asks_ends_the_job_and_x1_writes_nothing(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, connection = setup
    document = await a_document(connection)
    job = await a_job(connection, document.id, document.owner_id)
    model = Model()

    async def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not is_profile(messages):
            await write_subtree(connection, document.id, by_hand())
        return model(messages, info)

    with pytest.raises(PermanentError) as ended:
        await extract_document(context_of(pool, tmp_path, answer, database_url), job)

    assert ended.value.code == "document_has_tree"
    assert await rows(
        connection, "SELECT outcome, result ->> 'failure' FROM extraction_run WHERE job_id = %s", job.id
    ) == [("failed", "document_has_tree")]
    assert await rows(connection, "SELECT title FROM document WHERE id = %s", document.id) == [(None,)]
    assert await rows(connection, "SELECT count(*) FROM node WHERE document_id = %s", document.id) == [(1,)]


async def test_the_extraction_is_a_model_job_the_worker_knows(
    setup: Any, tmp_path: Path, database_url: str
) -> None:
    pool, _ = setup

    assert KIND == "extract.run" and KIND in MODEL_JOB_KINDS
    assert KIND in make_handlers(context_of(pool, tmp_path, None, database_url))
