"""X4's answer for a unit read (plan M1 7b, F9): an answer for another unit than asked is none; the
statements of the unit's blocks alone (app/pipeline/statement_read.py); what it checked absent as
the docking points' IRIs, each once."""

from typing import Any
from uuid import UUID

import pytest

from app.conversion.base import Block
from app.pipeline.statement_read import StatementContext
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x4_read import WrongUnit, read_unit

CV = "https://w3id.org/wlo/curriculum/vocab#"


def block(block_id: str) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id, page=page, kind="text", text="Die Lernenden erklären.",
        bbox=(0, 0, 1, 1), font_size=10, bold=False, italic=False,
    )  # fmt: skip


BLOCKS = [block("p1-b1"), block("p2-b1"), block("p2-b2"), block("p3-b1")]
UNIT = WorkPackage("E2", UUID(int=7), 1, 2, "p2-b1", "p2-b2", (2, 2), ("Optik",), "full", "statements")
CONTEXT = StatementContext(
    stage="x4",
    document_id=UUID(int=1),
    blocks=BLOCKS,
    printed=[],
    subkinds={},
    refines={},
    codes={
        "StatementKinds": {"learningOutcome": CV + "kind_learningOutcome"},
        "Addressees": {"learner": CV + "addr_learner"},
        "DockingPoints": {"level": CV + "dock_level", "time": CV + "dock_time"},
    },
)


def statement(block_id: str) -> dict[str, Any]:
    return {
        "blockIds": [block_id], "verbatim": "erklären", "leadIn": None, "statementKind": "learningOutcome",
        "statementSubkind": None, "addressee": "learner", "obligation": None, "layoutMarkers": [],
        "codeText": None, "levelText": None, "timeText": None, "contextText": None, "referenceMarker": None,
        "exampleText": None, "purposeText": None, "crossCuttingMarkers": [], "targetsContent": [],
    }  # fmt: skip


def test_the_statements_of_the_unit_s_blocks_and_what_it_checked_absent_are_read() -> None:
    read = read_unit(
        {
            "unitKey": "E2",
            "statements": [statement("p2-b2"), statement("p3-b1"), statement("p2-b1")],
            "checkedAbsent": ["time", "level", "time", "context"],
        },
        CONTEXT,
        UNIT,
    )

    assert [(item.first, item.draft.anchors[0].block_ids) for item in read.statements] == [
        (1, ("p2-b1",)),
        (2, ("p2-b2",)),
    ]
    assert read.checked_absent == (CV + "dock_time", CV + "dock_level")
    assert [finding.rule for finding in read.findings] == [
        "x4.block_outside_unit", "x4.statement_without_block", "x4.unknown_value",
    ]  # fmt: skip


@pytest.mark.parametrize("key", ["E3", "", "e2"])
def test_an_answer_for_another_unit_is_none(key: str) -> None:
    with pytest.raises(WrongUnit):
        read_unit({"unitKey": key, "statements": [], "checkedAbsent": []}, CONTEXT, UNIT)


def test_a_key_given_with_spaces_about_it_is_the_unit_s() -> None:
    read = read_unit({"unitKey": " E2 ", "statements": [], "checkedAbsent": []}, CONTEXT, UNIT)

    assert (read.statements, read.checked_absent, read.findings) == ([], (), [])
