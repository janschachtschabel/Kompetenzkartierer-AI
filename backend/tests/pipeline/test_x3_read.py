"""X3's answer read (plan M1 7b, F2): each model, operator, legend entry and rule a frame part - its
schema object without the blocks it names, which its anchor holds -, in the document's order; the
statements of the frame at the node of the range their first block lies in, from position 1 on;
what is checked absent; findings for what cannot be kept."""

from typing import Any
from uuid import UUID

from app.conversion.base import Block
from app.domain.l1 import AnchorDraft
from app.pipeline.statement_read import StatementContext
from app.pipeline.x2_segments import WorkPackage
from app.pipeline.x3_read import FrameContext, read_frame

CV = "https://w3id.org/wlo/curriculum/vocab#"
DOCUMENT, FRAME, OTHER_FRAME = UUID(int=1), UUID(int=3), UUID(int=4)


def block(block_id: str, words: str) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id, page=page, kind="text", text=words,
        bbox=(0, 0, 1, 1), font_size=10, bold=False, italic=False,
    )  # fmt: skip


BLOCKS = [
    block("p1-b1", "Kernlehrplan Physik"),  # 0  E0, the title pages
    block("p2-b1", "Kompetenzen"),  # 1  E1, read by X4
    block("p2-b2", "Die Schülerinnen und Schüler erklären."),  # 2
    block("p3-b1", "Leistungsbewertung"),  # 3  E2, a frame part
    block("p3-b2", "Die Leistung wird in allen Bereichen bewertet."),  # 4
    block("p3-b3", "beschreiben: darstellen (AFB I)"),  # 5
    block("p4-b1", "Anhang"),  # 6  E3, a frame part
    block("p4-b2", "Legende: L BNE Bildung für nachhaltige Entwicklung"),  # 7
]


def package(key: str, node: UUID | None, first: int, last: int, job: Any = "frame") -> WorkPackage:
    depth: Any = "typed" if job == "frame" else "full"
    return WorkPackage(key, node, first, last, BLOCKS[first].id, BLOCKS[last].id, (1, 1), (), depth, job)


RANGES = [package("E0", None, 0, 0), package("E2", FRAME, 3, 5), package("E3", OTHER_FRAME, 6, 7)]
CONTEXT = FrameContext(
    statements=StatementContext(
        stage="x3",
        document_id=DOCUMENT,
        blocks=BLOCKS,
        printed=[],
        subkinds={},
        refines={},
        codes={
            "StatementKinds": {name: CV + "kind_" + name for name in ("mandate", "content", "guidance")},
            "Addressees": {"educator": CV + "addr_educator"},
        },
    ),
    ranges=RANGES,
)


def statement(
    block_id: str, verbatim: str, kind: str = "mandate", targets: list[int] | None = None
) -> dict[str, Any]:
    return {
        "blockIds": [block_id], "verbatim": verbatim, "leadIn": None, "statementKind": kind,
        "statementSubkind": None, "addressee": "educator", "obligation": None, "layoutMarkers": [],
        "codeText": None, "levelText": None, "timeText": None, "contextText": None, "referenceMarker": None,
        "exampleText": None, "purposeText": None, "crossCuttingMarkers": [], "targetsContent": targets or [],
    }  # fmt: skip


def answer(**given: Any) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "competencyModels": [], "levelModels": [], "operators": [], "crossCuttingLegend": [], "rules": [],
        "statements": [], "checkedAbsent": [],
    }  # fmt: skip
    return empty | given


def rules(findings: list[Any]) -> list[str]:
    return [finding.rule for finding in findings]


def test_each_entry_is_a_frame_part_without_its_blocks_in_the_document_s_order() -> None:
    read = read_frame(
        answer(
            operators=[
                {
                    "lemma": "beschreiben",
                    "definition": "darstellen",
                    "taskDemandText": "I",
                    "evidenceBlockId": "p3-b3",
                }
            ],
            crossCuttingLegend=[
                {
                    "marker": "L BNE",
                    "label": "Bildung für nachhaltige Entwicklung",
                    "evidenceBlockId": "p4-b2",
                },
                {"marker": "L MB", "label": "Medienbildung", "evidenceBlockId": "p4-b2"},
            ],
            competencyModels=[
                {"title": "Kompetenzbereiche", "dimensions": [], "evidenceBlockIds": ["p9-b9", "p2-b1"]},
                {"title": "Erfunden", "dimensions": [], "evidenceBlockIds": ["p9-b9"]},
            ],
            rules=[{"blockIds": ["p3-b2"], "verbatim": "Bewertet wird alles.", "ruleKind": "completion"}],
        ),
        CONTEXT,
    )

    assert [(part.kind, dict(part.content), part.anchor.block_ids) for part in read.parts] == [
        ("competencyModels", {"title": "Kompetenzbereiche", "dimensions": []}, ("p2-b1",)),
        ("rules", {"verbatim": "Bewertet wird alles.", "ruleKind": "completion"}, ("p3-b2",)),
        (
            "operators",
            {"lemma": "beschreiben", "definition": "darstellen", "taskDemandText": "I"},
            ("p3-b3",),
        ),
        (
            "crossCuttingLegend",
            {"marker": "L BNE", "label": "Bildung für nachhaltige Entwicklung"},
            ("p4-b2",),
        ),
        ("crossCuttingLegend", {"marker": "L MB", "label": "Medienbildung"}, ("p4-b2",)),
    ]
    assert read.parts[0].anchor == AnchorDraft(("p2-b1",), page_start=2)
    assert {(part.origin, part.review_status) for part in read.parts} == {
        (CV + "orig_model", CV + "rev_proposed")
    }
    assert rules(read.findings) == ["x3.unknown_block", "x3.unknown_block", "x3.part_without_block"]
    assert read.counts == {"competencyModels": 1, "rules": 1, "operators": 1, "crossCuttingLegend": 2}


def test_a_statement_of_the_frame_stands_at_the_node_of_its_range_one_outside_is_left_out() -> None:
    read = read_frame(
        answer(
            statements=[
                statement("p4-b1", "Querschnitt beachten."),  # E3, at its first block
                statement("p3-b2", "Die Leistung wird bewertet."),  # E2
                statement("p2-b2", "Die Schülerinnen und Schüler erklären."),  # E1: X4's
                statement("p1-b1", "Kernlehrplan Physik"),  # E0: the title pages, of no node
                statement("p3-b3", "beschreiben", kind="guidance"),  # E2
            ]
        ),
        CONTEXT,
    )

    assert {node: [draft.verbatim for draft in drafts] for node, drafts in read.statements.items()} == {
        FRAME: ["Die Leistung wird bewertet.", "beschreiben"],
        OTHER_FRAME: ["Querschnitt beachten."],
    }
    # the title pages are a range of the frame, but no node holds a statement of them; E1 is X4's
    assert rules(read.findings) == ["x3.statement_without_node", "x3.statement_outside_frame"]


def test_a_statement_points_to_content_at_its_own_node_by_its_position() -> None:
    read = read_frame(
        answer(
            statements=[
                statement("p3-b2", "Bewertet wird.", targets=[1, 2]),
                statement("p3-b3", "beschreiben", kind="content"),  # E2: position 2
                statement("p4-b2", "Querschnitt.", kind="content"),  # E3: another node
            ]
        ),
        CONTEXT,
    )

    assert dict(read.statements[FRAME][0].details) == {"targetsContent": [2]}
    assert rules(read.findings) == ["x3.target_elsewhere"]


def test_what_the_document_does_not_say_is_kept_once() -> None:
    read = read_frame(answer(checkedAbsent=["level", "time", "level"]), CONTEXT)

    assert (read.checked_absent, read.parts, read.statements, read.findings) == (
        ("level", "time"),
        [],
        {},
        [],
    )
