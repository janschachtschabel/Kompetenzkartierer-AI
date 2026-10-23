"""What a profile value must be, and what a drafted node, statement and anchor must carry (plan M1 4.5)."""

import pytest

from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft, check_profile_value

PROFILE = {"schul:Inhaltsbereich": ("cv:fn_area",), "schul:Kompetenzerwartung": ("cv:kind_learningOutcome",)}


def anchor(**changes: object) -> AnchorDraft:
    values: dict[str, object] = {"block_ids": ("p3-b2",), "page_start": 3}
    return AnchorDraft(**(values | changes))  # type: ignore[arg-type]


def statement(**changes: object) -> StatementDraft:
    values: dict[str, object] = {
        "verbatim": "Die Lernenden planen ihre Arbeit.",
        "kind": "cv:kind_learningOutcome",
        "addressees": ("cv:addr_learner",),
        "anchors": (anchor(),),
        "origin": "cv:orig_source",
        "review_status": "cv:rev_proposed",
    }
    return StatementDraft(**(values | changes))  # type: ignore[arg-type]


def test_a_profile_value_under_its_core_value_fits() -> None:
    assert check_profile_value("schul:Inhaltsbereich", "cv:fn_area", PROFILE) is None


def test_a_profile_value_under_another_core_value_is_the_wrong_core() -> None:
    assert check_profile_value("schul:Inhaltsbereich", "cv:fn_unit", PROFILE) == "wrong_core"


def test_a_value_of_another_profile_is_not_in_the_profile() -> None:
    assert check_profile_value("beruf:Lernfeld", "cv:fn_unit", PROFILE) == "not_in_profile"


def test_an_anchor_with_a_printed_page_alone_is_one() -> None:
    assert anchor(page_start=None, printed_page="IV").printed_page == "IV"


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"page_start": None}, "page"),
        ({"page_start": 0}, "page"),
        ({"page_start": 4, "page_end": 3}, "page"),
        ({"block_ids": ("3-2",)}, "block"),
        ({"block_ids": ()}, "block"),
        ({"match_score": 1.5}, "score"),
        ({"table_cell": "r1c1"}, "cell"),
    ],
)
def test_an_anchor_without_its_place_or_with_a_wrong_one_is_refused(
    changes: dict[str, object], says: str
) -> None:
    with pytest.raises(ValueError, match=says):
        anchor(**changes)


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"verbatim": "  "}, "wording"),
        ({"addressees": ()}, "addressee"),
        ({"anchors": ()}, "anchor"),
    ],
)
def test_a_statement_without_wording_addressee_or_anchor_is_refused(
    changes: dict[str, object], says: str
) -> None:
    with pytest.raises(ValueError, match=says):
        statement(**changes)


def test_a_node_holds_its_statements_and_children_in_their_order() -> None:
    child = NodeDraft(
        function="cv:fn_unit", origin="cv:orig_source", review_status="cv:rev_proposed", code="LF 1"
    )
    node = NodeDraft(
        function="cv:fn_area",
        origin="cv:orig_source",
        review_status="cv:rev_proposed",
        statements=(statement(), statement(verbatim="Sie prüfen sie.")),
        children=(child,),
    )

    assert [found.verbatim for found in node.statements] == [
        "Die Lernenden planen ihre Arbeit.",
        "Sie prüfen sie.",
    ]
    assert node.children == (child,)


def test_a_node_whose_code_was_assigned_has_one() -> None:
    with pytest.raises(ValueError, match="assigned"):
        NodeDraft(
            function="cv:fn_unit", origin="cv:orig_rule", review_status="cv:rev_proposed", code_assigned=True
        )
