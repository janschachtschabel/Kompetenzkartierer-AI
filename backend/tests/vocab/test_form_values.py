"""What an edit sets, checked against the editor's form (plan M1 9.3, 9.4; app/vocab/form_values.py): a
field the form has, a text within its length, one a store keeps, and given where the form asks for it, a
list's value one
the form offers, a field of many a list of them each once; a node type or subkind under the function or
kind beside it, where the edit names either."""

from typing import Any

import pytest

from app.vocab.form_values import FieldError, check_under, checked
from app.vocab.forms import NODE_FIELDS, STATEMENT_FIELDS, Form
from app.vocab.lookup import ConceptDetails

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"


def concept(iri: str, *broader: str) -> ConceptDetails:
    return ConceptDetails(iri, None, iri.rsplit("#", 1)[-1], (), None, None, None, (), broader, False)


FORM = Form(
    "school",
    SCHOOL + "Terminology",
    NODE_FIELDS,
    STATEMENT_FIELDS,
    {
        "function": (concept(CV + "fn_area"), concept(CV + "fn_unit")),
        "node_type": (concept(SCHOOL + "Inhaltsbereich", CV + "fn_area"),),
        "obligation": (concept(CV + "obl_binding"),),
        "statement_kind": (concept(CV + "kind_learningOutcome"), concept(CV + "kind_content")),
        "subkind": (concept(SCHOOL + "Kompetenzerwartung", CV + "kind_learningOutcome"),),
        "addressees": (concept(CV + "addr_learner"), concept(CV + "addr_educator")),
    },
)


def problem(fields: Any, given: dict[str, Any]) -> tuple[str, str]:
    with pytest.raises(FieldError) as raised:
        checked(fields, FORM, given)
    return raised.value.key, raised.value.problem


def test_the_fields_an_edit_sets_come_back_as_they_are_stored() -> None:
    given = {
        "original_title": "Optik", "function": CV + "fn_area", "node_type": SCHOOL + "Inhaltsbereich",
        "code": "   ", "obligation": None,
    }  # fmt: skip

    assert checked(NODE_FIELDS, FORM, given) == {
        "original_title": "Optik", "function": CV + "fn_area", "node_type": SCHOOL + "Inhaltsbereich",
        "code": None, "obligation": None,  # a blank text is none
    }  # fmt: skip
    assert checked(STATEMENT_FIELDS, FORM, {"addressees": [CV + "addr_learner", CV + "addr_learner"]}) == {
        "addressees": [CV + "addr_learner"]  # each once
    }
    assert checked(STATEMENT_FIELDS, FORM, {"verbatim": "  Sie messen. "}) == {"verbatim": "  Sie messen. "}


def test_a_field_the_form_has_not_is_refused() -> None:
    assert problem(NODE_FIELDS, {"title": "Optik"}) == ("title", "unknown")
    assert problem(NODE_FIELDS, {"verbatim": "Sie messen."}) == ("verbatim", "unknown")  # a statement's


def test_a_field_the_form_asks_for_is_given() -> None:
    assert problem(NODE_FIELDS, {"original_title": " "}) == ("original_title", "required")
    assert problem(NODE_FIELDS, {"function": None}) == ("function", "required")
    assert problem(STATEMENT_FIELDS, {"addressees": []}) == ("addressees", "required")
    assert problem(STATEMENT_FIELDS, {"verbatim": None}) == ("verbatim", "required")


def test_a_value_of_the_wrong_shape_is_refused() -> None:
    assert problem(NODE_FIELDS, {"original_title": ["Optik"]}) == ("original_title", "not_text")
    assert problem(NODE_FIELDS, {"function": 3}) == ("function", "not_text")
    assert problem(STATEMENT_FIELDS, {"addressees": CV + "addr_learner"}) == ("addressees", "not_list")
    assert problem(STATEMENT_FIELDS, {"addressees": [None]}) == ("addressees", "not_offered")


def test_a_text_longer_than_its_field_holds_is_refused() -> None:
    assert checked(NODE_FIELDS, FORM, {"code": "x" * 100}) == {"code": "x" * 100}
    assert problem(NODE_FIELDS, {"code": "x" * 101}) == ("code", "too_long")
    assert problem(STATEMENT_FIELDS, {"verbatim": "x" * 20_001}) == ("verbatim", "too_long")


def test_a_text_no_store_keeps_is_refused() -> None:
    # PostgreSQL's text takes no NUL, UTF-8 no lone surrogate: either was a 500 at the write
    assert problem(NODE_FIELDS, {"original_title": "Op\x00tik"}) == ("original_title", "not_storable")
    assert problem(STATEMENT_FIELDS, {"verbatim": "Sie messen\ud800."}) == ("verbatim", "not_storable")
    assert problem(STATEMENT_FIELDS, {"codeText": "\x00"}) == ("codeText", "not_storable")


def test_a_value_the_form_does_not_offer_is_refused() -> None:
    assert problem(NODE_FIELDS, {"function": CV + "fn_grouping"}) == ("function", "not_offered")
    assert problem(NODE_FIELDS, {"obligation": CV + "obl_elective"}) == ("obligation", "not_offered")
    assert problem(STATEMENT_FIELDS, {"addressees": [CV + "addr_learner", CV + "addr_parent"]}) == (
        "addressees",
        "not_offered",
    )


def test_a_node_type_or_subkind_stands_under_the_function_or_kind_beside_it() -> None:
    area = {"function": CV + "fn_area", "node_type": SCHOOL + "Inhaltsbereich"}
    check_under(FORM, area, given=set(area))
    with pytest.raises(FieldError) as raised:
        check_under(FORM, area | {"function": CV + "fn_unit"}, given={"function"})
    assert (raised.value.key, raised.value.problem) == ("node_type", "not_under")
    with pytest.raises(FieldError) as raised:
        check_under(
            FORM,
            {"statement_kind": CV + "kind_content", "subkind": SCHOOL + "Kompetenzerwartung"},
            given={"subkind"},
        )
    assert (raised.value.key, raised.value.problem) == ("subkind", "not_under")


def test_a_pair_the_edit_names_not_is_left_as_it_stands() -> None:
    # a node type the profile no longer offers stays, unless the edit names it or its function
    kept = {"function": CV + "fn_unit", "node_type": SCHOOL + "Gone", "code": "1"}
    check_under(FORM, kept, given={"code"})

    with pytest.raises(FieldError) as raised:
        check_under(FORM, kept, given={"function"})
    assert (raised.value.key, raised.value.problem) == ("node_type", "not_offered")
