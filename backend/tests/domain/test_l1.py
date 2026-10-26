"""What a profile value must be, and what a drafted node, statement and anchor must carry (plan M1 4.5)."""

import uuid
from pathlib import Path

import pytest

from app.domain.l1 import REVIEW_STATUSES, AnchorDraft, NodeDraft, StatementDraft, check_profile_value
from app.vocab.loader import read_vocabulary

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"

NOT_FOUND = "https://w3id.org/wlo/curriculum/vocab#match_notFound"
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


def test_a_wording_not_found_is_anchored_at_its_page_without_blocks() -> None:
    # plan M1 8.1, 9.4: where the blocks hold no fitting passage, the page stays
    assert anchor(block_ids=(), match_kind=NOT_FOUND).page_start == 3


def test_a_draft_names_each_block_and_addressee_once_in_its_order() -> None:
    found = statement(
        addressees=("cv:addr_teacher", "cv:addr_learner", "cv:addr_teacher"),
        anchors=(anchor(block_ids=("p3-b2", "p3-b1", "p3-b2")),),
    )

    assert found.addressees == ("cv:addr_teacher", "cv:addr_learner")
    assert found.anchors[0].block_ids == ("p3-b2", "p3-b1")


def test_a_node_applies_to_each_once_in_its_order() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()

    node = NodeDraft(
        function="cv:fn_area",
        origin="cv:orig_source",
        review_status="cv:rev_proposed",
        applies_to=(second, first, second),
    )

    assert node.applies_to == (second, first)


def test_a_wording_that_is_no_text_is_refused() -> None:
    with pytest.raises(ValueError, match="surrogate"):
        statement(verbatim="Die Lernenden \ud800planen")


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"page_start": None}, "page"),
        ({"page_start": 0}, "page"),
        ({"page_start": 4, "page_end": 3}, "page"),
        ({"page_start": None, "printed_page": "IV", "page_end": 5}, "page"),  # an end without its start
        ({"block_ids": ("3-2",)}, "block"),
        ({"block_ids": ()}, "block"),
        ({"block_ids": (), "match_kind": NOT_FOUND, "page_start": None, "printed_page": "IV"}, "page"),
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


def test_the_review_statuses_are_those_of_the_vocabulary() -> None:
    scheme = "https://w3id.org/wlo/curriculum/vocab#ReviewStatuses"

    held = [iri for iri, concept in read_vocabulary(ONTOLOGY).concepts.items() if concept.scheme == scheme]

    assert sorted(REVIEW_STATUSES) == sorted(held)
