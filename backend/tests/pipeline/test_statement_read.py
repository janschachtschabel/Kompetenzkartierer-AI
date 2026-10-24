"""Statements as X3 and X4 read them from an answer (plan M1 7b, F9; konzept §7, §13.1): only blocks of
the conversion and of the range asked about; a wording field only where it stands in the statement's
own blocks - a value from the surroundings is inherited, never stored as wording -; codes to the
vocabularies' IRIs, a subkind only under its kind; origin model, proposed; in the document's order,
the content they point to by their place in it; at most MOST_STATEMENTS."""

from dataclasses import replace
from typing import Any
from uuid import UUID

from app.conversion.base import Block, Cell
from app.domain.l1 import AnchorDraft
from app.pipeline.statement_read import MOST_STATEMENTS, StatementContext, read_statements

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
DOCUMENT = UUID(int=1)


def block(block_id: str, words: str) -> Block:
    page = int(block_id[1 : block_id.index("-")])
    return Block(
        id=block_id, page=page, kind="text", text=words,
        bbox=(0, 0, 1, 1), font_size=10, bold=False, italic=False,
    )  # fmt: skip


BLOCKS = [
    block("p1-b1", "Optik"),  # 0
    block("p1-b2", "Die Schülerinnen und Schüler"),  # 1
    block("p2-b1", "(3) beschreiben  Licht, z. B. an Spiegeln (Klasse 7)."),  # 2
    block("p2-b2", "Lichtquellen"),  # 3
    block("p3-b1", "Schatten"),  # 4
]


def codes(scheme: str, *names: str, prefix: str) -> dict[str, dict[str, str]]:
    return {scheme: {name: CV + prefix + name for name in names}}


CONTEXT = StatementContext(
    stage="x4",
    document_id=DOCUMENT,
    blocks=BLOCKS,
    printed=[None, "12", "13"],
    subkinds={"U1": SCHOOL + "Kompetenzerwartung", "U2": SCHOOL + "Inhalt"},
    refines={
        SCHOOL + "Kompetenzerwartung": (CV + "kind_learningOutcome",),
        SCHOOL + "Inhalt": (CV + "kind_content",),
    },
    codes=codes("StatementKinds", "learningOutcome", "content", "unclassified", prefix="kind_")
    | codes("Addressees", "learner", "educator", prefix="addr_")
    | codes("Obligations", "binding", prefix="obl_")
    | {"LayoutMarkers": {"bullet": CV + "lm_bullet", "numbered": CV + "lm_numbered"}},
)


def given(**values: Any) -> dict[str, Any]:
    statement: dict[str, Any] = {
        "blockIds": ["p2-b1"],
        "verbatim": "beschreiben Licht",
        "leadIn": None,
        "statementKind": "learningOutcome",
        "statementSubkind": None,
        "addressee": "learner",
        "obligation": None,
        "layoutMarkers": [],
        "codeText": None,
        "levelText": None,
        "timeText": None,
        "contextText": None,
        "referenceMarker": None,
        "exampleText": None,
        "purposeText": None,
        "crossCuttingMarkers": [],
        "targetsContent": [],
    }
    return statement | values


def rules(findings: list[Any]) -> list[str]:
    return [finding.rule for finding in findings]


def test_a_statement_is_read_with_its_codes_its_wording_and_its_anchor() -> None:
    read, findings = read_statements(
        [
            given(
                blockIds=["p2-b1", "p2-b2"],
                verbatim="beschreiben Licht",
                leadIn="Die Schülerinnen und Schüler",
                statementSubkind="U1",
                obligation="binding",
                layoutMarkers=["numbered"],
                codeText="(3)",
                exampleText="z. B. an  Spiegeln",  # its spaces as the model gave them
                timeText="KLASSE 7",
                crossCuttingMarkers=["L BNE"],
            )
        ],
        CONTEXT,
        within=range(1, 4),
    )

    assert findings == []
    [statement] = read
    assert statement.first == 2
    draft = statement.draft
    assert (draft.verbatim, draft.lead_in, draft.kind, draft.subkind, draft.addressees, draft.obligation) == (
        "beschreiben Licht", "Die Schülerinnen und Schüler", CV + "kind_learningOutcome",
        SCHOOL + "Kompetenzerwartung", (CV + "addr_learner",), CV + "obl_binding",
    )  # fmt: skip
    assert draft.layout_markers == (CV + "lm_numbered",)
    assert dict(draft.details) == {
        "codeText": "(3)",
        "exampleText": "z. B. an  Spiegeln",
        "timeText": "KLASSE 7",
        "crossCuttingMarkers": ["L BNE"],
    }
    assert draft.anchors == (AnchorDraft(("p2-b1", "p2-b2"), page_start=2, printed_page="12"),)
    assert (draft.origin, draft.review_status, draft.rule_id) == (
        CV + "orig_model",
        CV + "rev_proposed",
        None,
    )


def test_an_anchor_over_two_pages_names_both() -> None:
    read, _ = read_statements([given(blockIds=["p2-b2", "p3-b1"])], CONTEXT, within=None)

    assert read[0].draft.anchors == (
        AnchorDraft(("p2-b2", "p3-b1"), page_start=2, page_end=3, printed_page="12"),
    )


def test_a_value_from_the_surroundings_is_not_stored_as_wording() -> None:
    # "Optik" is the section's heading, "Klasse 5" stands nowhere: both would be inherited, not read
    read, findings = read_statements(
        [given(contextText="Optik", levelText="Klasse 5", codeText="(3)")], CONTEXT, within=range(0, 5)
    )

    assert dict(read[0].draft.details) == {"codeText": "(3)"}
    assert rules(findings) == ["x4.value_from_surroundings", "x4.value_from_surroundings"]
    assert {finding.severity for finding in findings} == {"info"}


def test_only_blocks_of_the_conversion_and_the_range_hold_a_statement() -> None:
    read, findings = read_statements(
        [
            given(blockIds=["p1-b1", "p2-b1", "p9-b9"]),  # before the range, in it, none of the conversion
            given(blockIds=["p3-b1"], verbatim="Schatten"),  # after it: nothing is left of it
        ],
        CONTEXT,
        within=range(1, 4),
    )

    assert [statement.draft.anchors[0].block_ids for statement in read] == [("p2-b1",)]
    assert rules(findings) == [
        "x4.block_outside_unit", "x4.unknown_block", "x4.block_outside_unit", "x4.statement_without_block",
    ]  # fmt: skip


def test_any_block_of_the_conversion_holds_one_where_no_range_is_asked_about() -> None:
    read, findings = read_statements([given(blockIds=["p3-b1"], verbatim="Schatten")], CONTEXT, within=None)

    assert (len(read), findings) == (1, [])


def test_a_subkind_holds_only_under_its_kind_and_by_a_key_the_question_listed() -> None:
    read, findings = read_statements(
        [given(statementSubkind="U2"), given(statementSubkind="U9")], CONTEXT, within=None
    )

    assert [statement.draft.subkind for statement in read] == [None, None]
    assert rules(findings) == ["x4.subkind_mismatch", "x4.unknown_key"]


def test_a_statement_of_an_unknown_kind_or_addressee_is_left_out_an_unknown_obligation_or_marker_unset() -> (
    None
):
    read, findings = read_statements(
        [
            given(statementKind="standard"),
            given(addressee="family"),
            given(obligation="elective", layoutMarkers=["bullet", "box"]),
        ],
        CONTEXT,
        within=None,
    )

    [statement] = read
    assert (statement.draft.obligation, statement.draft.layout_markers) == (None, (CV + "lm_bullet",))
    assert rules(findings) == ["x4.unknown_value"] * 4


def test_statements_come_in_the_document_s_order_pointing_to_content_by_their_place() -> None:
    read, findings = read_statements(
        [
            given(blockIds=["p3-b1"], verbatim="Schatten", statementKind="content"),  # 0
            given(blockIds=["p2-b1"], targetsContent=[0, 2, 3, 9]),  # 1: to content, an outcome, one left out
            given(blockIds=["p2-b2"], verbatim="Lichtquellen", statementKind="learningOutcome"),  # 2
            given(blockIds=["p9-b1"]),  # 3: no block of the conversion
        ],
        CONTEXT,
        within=None,
    )

    assert [(statement.draft.verbatim, statement.targets) for statement in read] == [
        ("beschreiben Licht", (2,)),
        ("Lichtquellen", ()),
        ("Schatten", ()),
    ]
    assert rules(findings) == [
        "x4.unknown_block", "x4.statement_without_block",
        "x4.target_not_content", "x4.target_not_content", "x4.target_not_content",
    ]  # fmt: skip


def test_at_most_most_statements_are_read() -> None:
    read, findings = read_statements([given()] * (MOST_STATEMENTS + 2), CONTEXT, within=None)

    assert len(read) == MOST_STATEMENTS
    assert rules(findings) == ["x4.too_many_statements"]


def test_a_wording_too_long_for_the_store_is_left_out_a_lead_in_cut() -> None:
    read, findings = read_statements(
        [given(verbatim="x" * 20_001), given(leadIn="y" * 2_001)], CONTEXT, within=None
    )

    [statement] = read
    assert statement.draft.lead_in == "y" * 2_000
    assert rules(findings) == ["x4.statement_too_long", "x4.value_cut"]


def test_a_blank_wording_is_left_out_as_none() -> None:
    read, findings = read_statements([given(verbatim="  ")], CONTEXT, within=None)

    assert (read, rules(findings)) == ([], ["x4.statement_without_wording"])


def table(block_id: str, rows: list[list[str]]) -> Block:
    """A table whose first row is its header, as the conversion marks it."""
    page = int(block_id[1 : block_id.index("-")])
    cells = tuple(
        Cell(id=f"T1:r{r}c{c}", page=page, row=r, column=c, text=value, header=r == 1)
        for r, row in enumerate(rows, start=1)
        for c, value in enumerate(row, start=1)
    )
    return Block(
        id=block_id, page=page, kind="table", text="\n".join(" | ".join(row) for row in rows),
        bbox=(0, 0, 1, 1), font_size=None, bold=False, italic=False, cells=cells,
    )  # fmt: skip


def test_in_a_table_a_value_stands_only_in_the_statement_s_own_row_not_its_header() -> None:
    # the level a column's header names is inherited (konzept §13.1), not the statement's wording
    grid = table(
        "p1-b1",
        [["Kompetenzen", "Klasse 7/8"], ["beschreiben Licht", "Optik"], ["erklären Schatten", "Mechanik"]],
    )
    context = replace(CONTEXT, blocks=[grid])
    asked = given(
        blockIds=["p1-b1"], verbatim="beschreiben Licht", levelText="Klasse 7/8", contextText="Optik"
    )

    # one over two rows, which no row holds alone: the table's body, its header still not
    over_rows = given(blockIds=["p1-b1"], verbatim="beschreiben Licht Optik erklären", levelText="Klasse 7/8")

    read, findings = read_statements(
        [asked, given(blockIds=["p1-b1"], contextText="Mechanik"), over_rows], context, within=None
    )

    assert [dict(statement.draft.details) for statement in read] == [{"contextText": "Optik"}, {}, {}]
    assert rules(findings) == ["x4.value_from_surroundings"] * 3


def test_a_value_parted_at_a_line_s_end_or_by_a_soft_hyphen_stands_in_its_block() -> None:
    parted = block(
        "p1-b1", "Sie beschreiben in Alltags-\nsituationen und Na\N{SOFT HYPHEN}tur, was Licht tut."
    )
    context = replace(CONTEXT, blocks=[parted])

    read, findings = read_statements(
        [
            given(blockIds=["p1-b1"], contextText="in Alltagssituationen", exampleText="Natur"),
            given(blockIds=["p1-b1"], contextText="in Alltags-\nsituationen"),  # as the model copied it
        ],
        context,
        within=None,
    )

    assert ([dict(statement.draft.details) for statement in read], findings) == (
        [
            {"contextText": "in Alltagssituationen", "exampleText": "Natur"},
            {"contextText": "in Alltags-\nsituationen"},
        ],
        [],
    )
