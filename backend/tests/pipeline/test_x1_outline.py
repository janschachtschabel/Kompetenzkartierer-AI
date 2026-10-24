"""X1's outline (plan M1 6.4): the headings a strong pattern left untyped go to the model - their
title path, level and the opening of their section - and come back with a node type or a function;
what the answer leaves out or names wrongly is a finding, never a crash; the skeleton and the
decisions make the document's tree, each node anchored at its heading."""

from typing import Any, Literal
from uuid import UUID

from app.conversion.base import Block
from app.domain.l1 import AnchorDraft
from app.pipeline.prompts.x1_outline import outline_prompt
from app.pipeline.skeleton import Heading, Skeleton
from app.pipeline.toc import Contents
from app.pipeline.x1_outline import (
    OPENING_SIGNS,
    OUTLINE_BATCH,
    Decision,
    OutlineContext,
    batches,
    build_tree,
    decide,
    outline_items,
)
from app.vocab.lookup import ConceptText

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
DOCUMENT = UUID("01900000-0000-7000-8000-000000000001")
RULE = SCHOOL + "cue-ib-inhaltsfeld"
Kind = Literal["text", "page_header"]


def heading(key: str, position: int, title: str, parent: str | None = None, **changes: Any) -> Heading:
    values: dict[str, Any] = {
        "key": key, "position": position, "block_id": f"p{position + 1}-b1", "page": position + 1,
        "level": 1 if parent is None else 2, "parent": parent, "title": title, "code": key[1:],
        "code_assigned": True, "node_type": None, "rule_id": None,
    } | changes  # fmt: skip
    return Heading(**values)


def text(block_id: str, words: str, kind: Kind = "text") -> Block:
    return Block(
        id=block_id, page=int(block_id[1 : block_id.index("-")]), kind=kind, text=words,
        bbox=(0, 0, 1, 1), font_size=10, bold=False, italic=False,
    )  # fmt: skip


# H1 "Kompetenzen" (untyped) holds H2 "Inhaltsfeld 1: Optik" (typed by its pattern) and H3 "Hinweise"
HEADINGS = (
    heading("H1", 0, "Kompetenzen"),
    heading(
        "H2",
        1,
        "Inhaltsfeld 1: Optik",
        "H1",
        node_type=SCHOOL + "Inhaltsbereich",
        rule_id=RULE,
        code="1",
        code_assigned=False,
    ),
    heading("H3", 3, "Hinweise", "H1"),
)
SKELETON = Skeleton(HEADINGS, Contents((), frozenset()), 10, frozenset())
BLOCKS = [
    text("p1-b1", "Kompetenzen"),
    text("p2-b1", "Inhaltsfeld 1: Optik"),
    text("p2-b2", "Licht breitet sich aus. " * 20),
    text("p4-b1", "Hinweise"),
    text("p4-b2", "Kopfzeile", kind="page_header"),
    text("p4-b3", "Zur Leistungsbewertung."),
]
CONTEXT = OutlineContext(
    document_id=DOCUMENT,
    types={"T1": SCHOOL + "Inhaltsbereich", "T2": SCHOOL + "Rahmenteil"},
    functions_of={SCHOOL + "Inhaltsbereich": CV + "fn_area", SCHOOL + "Rahmenteil": CV + "fn_frame"},
    codes={
        "NodeFunctions": {
            name: CV + "fn_" + name for name in ("area", "frame", "grouping", "unit", "nonCurricular")
        },
        "ScopeShares": {"common": CV + "share_common"},
    },
    specifications=frozenset({"S1"}),
)


def test_only_the_headings_left_untyped_are_asked_with_their_path_and_opening() -> None:
    items = outline_items(SKELETON, BLOCKS)

    assert [(item.key, item.level, item.path) for item in items] == [
        ("H1", 1, "Kompetenzen"),
        ("H3", 2, "Kompetenzen / Hinweise"),
    ]
    assert items[0].opening == ""  # its first child follows at once
    assert items[1].opening == "Zur Leistungsbewertung."  # the header between is no text


def test_an_opening_is_cut_to_its_signs() -> None:
    long = Skeleton((heading("H1", 0, "Optik"),), Contents((), frozenset()), 10, frozenset())

    [item] = outline_items(long, [text("p1-b1", "Optik"), text("p1-b2", "x" * 1000)])

    assert item.opening == "x" * OPENING_SIGNS


def test_the_headings_are_asked_in_batches() -> None:
    many = tuple(heading(f"H{n}", n - 1, f"Titel {n}") for n in range(1, 121))
    items = outline_items(
        Skeleton(many, Contents((), frozenset()), 10, frozenset()),
        [text(f"p{n}-b1", f"Titel {n}") for n in range(1, 121)],
    )

    assert [len(batch) for batch in batches(items)] == [OUTLINE_BATCH, OUTLINE_BATCH, 120 - 2 * OUTLINE_BATCH]


def type_text(name: str, label: str, broader: str) -> ConceptText:
    return ConceptText(SCHOOL + name, None, label, f"Ein {label}.", (CV + broader,), "full")


def test_the_question_lists_the_types_with_their_functions_the_specifications_and_the_headings() -> None:
    prompt, types = outline_prompt(
        outline_items(SKELETON, BLOCKS),
        [
            type_text("Inhaltsbereich", "Inhaltsbereich", "fn_area"),
            type_text("Rahmenteil", "Rahmenteil", "fn_frame"),
        ],
        {CV + "fn_area": "area", CV + "fn_frame": "frame"},
        [("S1", "Physik")],
    )

    assert types == {"T1": SCHOOL + "Inhaltsbereich", "T2": SCHOOL + "Rahmenteil"}
    assert "T1: Inhaltsbereich (Kernfunktion area) — Ein Inhaltsbereich.\n" in prompt
    assert "S1: Physik\n" in prompt
    assert "H3 | Ebene 2 | Kompetenzen / Hinweise\nAnfang: Zur Leistungsbewertung.\n" in prompt
    assert "H2 " not in prompt  # typed by its pattern: not asked
    assert prompt.rstrip().endswith("Antworte im vorgegebenen Schema.")


def test_a_question_without_specifications_lists_none() -> None:
    prompt, _ = outline_prompt(outline_items(SKELETON, BLOCKS), [], {}, [])

    assert "SPEZIFIKATIONEN" not in prompt


def answer(
    key: str, node_type: str | None = None, function: str = "grouping", **changes: Any
) -> dict[str, Any]:
    return {
        "headingId": key,
        "nodeType": node_type,
        "nodeFunction": function,
        "appliesTo": [],
        "scopeShare": None,
    } | changes


def rules(findings: Any) -> list[tuple[str, str, str | None]]:
    return [(finding.rule, finding.severity, finding.path) for finding in findings]


def test_a_type_answered_gives_its_core_function_a_function_answered_stands_alone() -> None:
    decisions, findings = decide(
        SKELETON, ["H1", "H3"], [answer("H1", function="area"), answer("H3", "T2", function="unit")], CONTEXT
    )

    assert decisions["H1"] == Decision(None, CV + "fn_area", (), None, CV + "orig_model", None)
    assert decisions["H3"] == Decision(
        SCHOOL + "Rahmenteil", CV + "fn_frame", (), None, CV + "orig_model", None
    )
    assert findings == []


def test_a_heading_a_pattern_typed_is_the_rule_s_with_its_type_s_function() -> None:
    decisions, _ = decide(SKELETON, ["H1", "H3"], [answer("H1"), answer("H3")], CONTEXT)

    assert decisions["H2"] == Decision(
        SCHOOL + "Inhaltsbereich", CV + "fn_area", (), None, CV + "orig_rule", RULE
    )


def test_a_heading_the_answer_leaves_out_gets_a_function_by_its_children_and_a_finding() -> None:
    decisions, findings = decide(SKELETON, ["H1", "H3"], [], CONTEXT)

    assert decisions["H1"].function == CV + "fn_grouping"  # it holds headings
    assert decisions["H3"].function == CV + "fn_unit"
    assert (decisions["H3"].origin, decisions["H3"].rule_id) == (CV + "orig_rule", "x1.outline_unanswered")
    assert rules(findings) == [
        ("x1.outline_unanswered", "warning", "$.headings[H1]"),
        ("x1.outline_unanswered", "warning", "$.headings[H3]"),
    ]
    assert findings[0].focus_id == DOCUMENT


def test_what_the_answer_names_wrongly_is_a_finding_never_a_value() -> None:
    decisions, findings = decide(
        SKELETON,
        ["H1", "H3"],
        [
            answer("H1", "T9", function="area", appliesTo=["S1", "S7"], scopeShare="common"),
            answer("H1", function="unit"),  # a second answer of one heading
            answer("H8"),  # a heading not asked
            answer("H3", function="frame"),
        ],
        CONTEXT,
    )

    assert decisions["H1"] == Decision(
        None, CV + "fn_area", ("S1",), CV + "share_common", CV + "orig_model", None
    )
    assert rules(findings) == [
        ("x1.unknown_key", "warning", "$.headings[0].nodeType"),
        ("x1.unknown_key", "warning", "$.headings[0].appliesTo[1]"),
        ("x1.duplicate_key", "warning", "$.headings[1].headingId"),
        ("x1.unknown_key", "warning", "$.headings[2].headingId"),
    ]


def test_the_tree_nests_the_headings_each_anchored_at_its_block() -> None:
    decisions, _ = decide(
        SKELETON, ["H1", "H3"], [answer("H1", appliesTo=["S1"]), answer("H3", function="frame")], CONTEXT
    )
    spec = UUID("01900000-0000-7000-8000-0000000000aa")

    [root] = build_tree(SKELETON, decisions, {"S1": spec})

    assert (root.original_title, root.function, root.code, root.code_assigned, root.applies_to) == (
        "Kompetenzen", CV + "fn_grouping", "1", True, (spec,),
    )  # fmt: skip
    assert root.anchors == (AnchorDraft(block_ids=("p1-b1",), page_start=1, quote="Kompetenzen"),)
    typed, notes = root.children
    assert (typed.node_type, typed.origin, typed.rule_id, typed.code, typed.code_assigned) == (
        SCHOOL + "Inhaltsbereich", CV + "orig_rule", RULE, "1", False,
    )  # fmt: skip
    assert (notes.function, notes.origin, notes.review_status) == (
        CV + "fn_frame",
        CV + "orig_model",
        CV + "rev_proposed",
    )
    assert notes.extraction_depth is None  # its type's, or its function's, read where it is needed
