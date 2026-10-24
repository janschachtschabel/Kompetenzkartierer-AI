"""X1's profile of a document as a stage asks for it (plan M1 6.2): the question built from the
document, its blocks and its sector's profile and lexicon; a model's answer of the schema's form
read against it and written - with a model standing in (FunctionModel), never a provider."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from app.conversion.base import Block
from app.db.migrate import migrate
from app.db.profile import write_profile
from app.domain.lexicon import active_cues
from app.llm.calls import ask, build_agent
from app.llm.schema import load_schema
from app.pipeline.prompts.x1_profile import INSTRUCTIONS, SCHEMA, SCHEMA_NAME
from app.pipeline.toc import Contents
from app.pipeline.x1_profile import read_profile
from app.pipeline.x1_question import profile_question
from app.vocab.loader import read_vocabulary
from app.vocab.lookup import cues_for
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of
from tests.llm.test_calls import Ledger

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
REGION = "https://w3id.org/wlo/curriculum/region/"


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


def block(block_id: str, words: str) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id,
        page=page,
        kind="text",
        text=words,
        bbox=(0, 0, 1, 1),
        font_size=10,
        bold=False,
        italic=False,
    )


BLOCKS = [
    block("p1-b1", "Kernlehrplan für die Sekundarstufe I Physik"),
    block("p1-b2", "Ministerium für Schule und Bildung des Landes Nordrhein-Westfalen"),
    block("p2-b1", "Dieser Kernlehrplan tritt am 1. August 2019 in Kraft."),
    block("p2-b2", "Die Inhaltsfelder ordnen die Kompetenzerwartungen."),
]


def key_of(keys: dict[str, str], iri: str) -> str:
    return next(key for key, named in keys.items() if named == iri)


async def test_a_document_s_profile_is_asked_read_and_written(connection: psycopg.AsyncConnection) -> None:
    document = await document_of(connection, BLOCKS, regions=("DE-NW",))
    cues = active_cues(await cues_for(connection, "school"), frozenset({REGION + "DE-NW"}), None, None)
    question = await profile_question(
        connection, document, BLOCKS, [None, None], Contents((), frozenset()), cues
    )
    lists = question.context.lists
    answer: dict[str, Any] = {
        "document": {
            "title": "Kernlehrplan für die Sekundarstufe I Physik",
            "documentType": key_of(dict(lists.document_types), SCHOOL + "dt-Lehrplan"),
            "legalForm": "administrativeRegulation",
            "documentBinding": "binding",
            "lifecycle": "inForce",
            "educationSectors": ["school"],
            "regions": ["DE-NW"],
            "issuerText": "Ministerium für Schule und Bildung des Landes Nordrhein-Westfalen",
            "issuedText": None,
            "validFromText": "1. August 2019",
            "editionText": None,
            "evidenceBlockIds": ["p1-b1", "p1-b2", "p2-b1"],
        },
        "specifications": [
            {
                "key": "S1",
                "kind": "curriculum",
                "title": "Physik",
                "fieldText": "Physik",
                "applicability": {
                    "sector": "school",
                    "formality": "formal",
                    "timeKind": "gradeLevel",
                    "timeText": "Sekundarstufe I",
                    "levelText": None,
                    "institutionText": None,
                    "targetGroupText": None,
                    "evidenceBlockIds": ["p1-b1"],
                },
                "variants": [],
            }
        ],
        "termMappings": [
            {
                "documentTerm": "Inhaltsfeld",
                "mapsTo": key_of(dict(lists.terms), SCHOOL + "Inhaltsbereich"),
                "evidenceBlockId": "p2-b2",
            }
        ],
        "newTerms": [],
    }
    asked: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        asked.append(str(messages[0].parts[-1].content))  # type: ignore[union-attr]
        args = json.dumps(answer)
        usage = RequestUsage(input_tokens=1_000, output_tokens=200)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)], usage=usage)

    stage = build_agent(
        FunctionModel(model, settings={"max_tokens": 4_000}),
        schema=load_schema(ONTOLOGY / "schemas", SCHEMA),
        name=SCHEMA_NAME,
        instructions=INSTRUCTIONS,
    )

    got = await ask(stage, question.prompt, meter=Ledger())
    assert got.output is not None
    profile = read_profile(got.output, question.context)
    async with connection.transaction():
        keys, _ = await write_profile(connection, document.id, profile)

    [prompt] = asked
    assert "[p2-b1] Dieser Kernlehrplan tritt am 1. August 2019 in Kraft." in prompt
    lehrplan = key_of(dict(lists.document_types), SCHOOL + "dt-Lehrplan")
    assert f"{lehrplan}: Lehrplan" in prompt
    assert f"„Kernlehrplan“ → {lehrplan}\n" in prompt  # NW's word for its Lehrplan
    assert "„LehrplanPLUS“" not in prompt  # Bavaria's word: a definition may name it, no cue does
    assert profile.findings == ()
    cursor = await connection.execute(
        "SELECT title, document_type_iri, valid_from, issuer FROM document WHERE id = %s", (document.id,)
    )
    assert await cursor.fetchone() == (
        "Kernlehrplan für die Sekundarstufe I Physik",
        SCHOOL + "dt-Lehrplan",
        "2019-08-01",
        "Ministerium für Schule und Bildung des Landes Nordrhein-Westfalen",
    )
    assert list(keys) == ["S1"]
