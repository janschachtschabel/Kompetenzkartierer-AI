"""X5's plausibility checks (plan M1 8.2), each a finding on the row it is about: a statement that is
its node's heading, a unit read whole that holds no statement, a rule whose bounds contradict, a value
the vocabularies have retired since it was written."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest

from app.conversion.base import Block
from app.db.frame_parts import FramePartDraft, write_frame_parts
from app.db.migrate import migrate
from app.db.nodes import write_subtree
from app.db.runs import RunStart, start_run
from app.db.units import mark_unit
from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft
from app.pipeline.x5_checks import plausibility
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
MODEL, PROPOSED = CV + "orig_model", CV + "rev_proposed"
AT = AnchorDraft(("p1-b1",), page_start=1)


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


async def a_document(connection: psycopg.AsyncConnection) -> Any:
    text = Block(
        id="p1-b1",
        page=1,
        kind="text",
        text="Kompetenzen",
        bbox=(0, 0, 1, 1),
        font_size=10,
        bold=False,
        italic=False,
    )
    return await document_of(connection, [text])


def statement(verbatim: str, **changes: Any) -> StatementDraft:
    return StatementDraft(
        verbatim=verbatim, kind=CV + "kind_learningOutcome", addressees=(CV + "addr_learner",), anchors=(AT,),
        origin=MODEL, review_status=PROPOSED, **changes,
    )  # fmt: skip


def node(title: str | None, *statements: StatementDraft, **changes: Any) -> NodeDraft:
    return NodeDraft(
        function=CV + "fn_area", origin=MODEL, review_status=PROPOSED, original_title=title, anchors=(AT,),
        statements=statements, **changes,
    )  # fmt: skip


async def ids(connection: psycopg.AsyncConnection, query: str, *params: Any) -> list[UUID]:
    cursor = await connection.execute(query, params)
    return [row[0] for row in await cursor.fetchall()]


async def a_run(connection: psycopg.AsyncConnection, document: Any, stage: Any) -> UUID:
    return await start_run(connection, RunStart(document.id, None, None, stage, None, None, None, None))


def ordered(items: Any) -> list[tuple[Any, ...]]:
    return sorted(items, key=str)  # details are dicts, which do not order


def seen(findings: Any) -> list[tuple[Any, ...]]:
    return ordered((found.rule, found.severity, found.focus_id, found.details) for found in findings)


async def test_a_statement_that_is_its_node_s_heading_is_a_warning(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await a_document(connection)
    tree = node("2.1 Kompetenzen", statement("Kompetenzen"), statement("Die Lernenden beschreiben Licht."))
    await write_subtree(connection, document.id, tree)
    [heading] = await ids(connection, "SELECT id FROM statement WHERE verbatim = 'Kompetenzen'")

    assert seen(await plausibility(connection, document.id)) == [
        ("x5.heading_as_statement", "warning", heading, {})
    ]  # the numbering aside, as the text hash reads it


async def test_a_unit_read_whole_that_holds_no_statement_is_noted_at_its_node(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await a_document(connection)
    held = await write_subtree(
        connection, document.id, node("Optik", statement("Die Lernenden beschreiben Licht."))
    )
    empty = await write_subtree(connection, document.id, node("Mechanik"))
    run = await a_run(connection, document, "X4")
    units: list[tuple[str, UUID | None, int, tuple[str, ...]]] = [
        ("E1", held, 1, ()),
        ("E2", empty, 0, ()),
        ("E3", None, 0, ()),
        ("E4", empty, 0, (CV + "dock_field",)),  # read whole and found what is absent: no finding
    ]
    for key, node_id, statements, absent in units:
        await mark_unit(
            connection,
            document.id,
            key,
            run_id=run,
            node_id=node_id,
            statements=statements,
            checked_absent=absent,
        )

    assert seen(await plausibility(connection, document.id)) == ordered(
        [
            ("x5.unit_without_statements", "info", empty, {"unit": "E2"}),
            ("x5.unit_without_statements", "info", document.id, {"unit": "E3"}),  # no node: the document
        ]
    )


RULE: dict[str, Any] = {
    "verbatim": "Regel.", "ruleKind": "selection", "minCount": None, "maxCount": None, "minAmount": None,
    "maxAmount": None, "amountUnit": None, "requirementKind": None, "maxShare": None, "optionTexts": [],
}  # fmt: skip


async def test_a_rule_whose_bounds_contradict_is_a_warning(connection: psycopg.AsyncConnection) -> None:
    document = await a_document(connection)
    run = await a_run(connection, document, "X3")
    contents = [
        RULE | {"minCount": 3, "maxCount": 2},
        RULE | {"minAmount": 10, "maxAmount": 5.5},
        RULE | {"maxShare": 1.5},
        RULE | {"maxShare": -0.1},
        RULE | {"minCount": 2, "maxCount": 2, "minAmount": 1, "maxAmount": 40, "maxShare": 0.5},  # fits
        RULE | {"minCount": 4},  # one bound alone contradicts nothing
        RULE | {"maxShare": 0},  # the ends of a share fit
        RULE | {"maxShare": 1},
    ]
    drafts = [
        FramePartDraft("rules", content, AT, origin=MODEL, review_status=PROPOSED) for content in contents
    ]
    parts = await write_frame_parts(connection, document.id, document.conversion_id, drafts, run_id=run)
    operator = {"lemma": "beschreiben", "definition": None, "taskDemandText": None}
    await write_frame_parts(
        connection, document.id, document.conversion_id,
        [FramePartDraft("operators", operator, AT, origin=MODEL, review_status=PROPOSED)], run_id=run,
    )  # fmt: skip

    assert seen(await plausibility(connection, document.id)) == ordered(
        [
            ("x5.rule_bounds", "warning", parts[0], {"minCount": 3, "maxCount": 2}),
            ("x5.rule_bounds", "warning", parts[1], {"minAmount": 10, "maxAmount": 5.5}),
            ("x5.rule_bounds", "warning", parts[2], {"maxShare": 1.5}),
            ("x5.rule_bounds", "warning", parts[3], {"maxShare": -0.1}),
        ]
    )


async def test_a_value_retired_since_it_was_written_is_a_warning(connection: psycopg.AsyncConnection) -> None:
    document = await a_document(connection)
    binding, outcome, expectation = (
        CV + "obl_binding",
        CV + "kind_learningOutcome",
        SCHOOL + "Kompetenzerwartung",
    )
    told = statement("Die Lernenden beschreiben Licht.", subkind=expectation, obligation=binding)
    tree = node("Optik", told, node_type=SCHOOL + "Inhaltsbereich", obligation=binding)
    node_id = await write_subtree(connection, document.id, tree)
    [statement_id] = await ids(connection, "SELECT id FROM statement WHERE document_id = %s", document.id)
    assert await plausibility(connection, document.id) == []  # nothing retired yet

    retired = [CV + "fn_area", SCHOOL + "Inhaltsbereich", binding, outcome, expectation]
    await connection.execute(
        "UPDATE vocab_concept SET retired_in = (SELECT max(id) FROM vocab_release) WHERE iri = ANY(%s)",
        (retired,),
    )

    found = await plausibility(connection, document.id)
    assert seen(found) == ordered(
        [("x5.retired_value", "warning", node_id, {"value": value}) for value in retired[:3]]
        + [("x5.retired_value", "warning", statement_id, {"value": value}) for value in retired[2:]]
    )
    assert ordered((item.focus_id, item.path, item.details["value"]) for item in found) == ordered(
        [
            (node_id, "cur:nodeFunction", retired[0]),
            (node_id, "cur:nodeType", retired[1]),
            (node_id, "cur:obligation", binding),
            (statement_id, "cur:obligation", binding),
            (statement_id, "cur:statementKind", outcome),
            (statement_id, "cur:statementSubkind", expectation),
        ]
    )  # the field each value stands in
