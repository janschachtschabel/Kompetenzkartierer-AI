"""X1's answer read into a document's profile (plan M1 6.2): its keys back to IRIs, its codes to the
vocabularies' values, its dates from their wording; what it names that the lists or the conversion
do not hold - and what differs from how the document was made - become findings, never values."""

import copy
from typing import Any
from uuid import UUID

import pytest

from app.domain.l1 import SpecificationDraft, VariantDraft
from app.pipeline.prompts.x1_profile import ProfileLists
from app.pipeline.x1_profile import ProfileContext, parse_date, read_profile

CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
DOCUMENT = UUID("01900000-0000-7000-8000-000000000001")
LISTS = ProfileLists(
    document_types={"D1": SCHOOL + "dt-Kernlehrplan", "D2": SCHOOL + "dt-Lehrplan"},
    terms={"T1": SCHOOL + "Inhaltsbereich", "T2": SCHOOL + "Kompetenzerwartung"},
)
CODES = {
    "LegalForms": {
        "administrativeRegulation": CV + "lf_administrativeRegulation",
        "unknown": CV + "lf_unknown",
    },
    "DocumentBindings": {"binding": CV + "bind_binding"},
    "Lifecycles": {"inForce": CV + "life_inForce"},
    "EducationSectors": {"school": CV + "sec_school", "vocational": CV + "sec_vocational"},
    "Formalities": {"formal": CV + "form_formal"},
    "TimeKinds": {"gradeLevel": CV + "time_gradeLevel"},
    "VariantKinds": {"track": CV + "var_track"},
    "NodeFunctions": {"grouping": CV + "fn_grouping"},
}
CONTEXT = ProfileContext(
    document_id=DOCUMENT,
    sector="school",
    regions=("DE-NW",),
    block_ids=frozenset({"p1-b1", "p1-b2", "p2-b1"}),
    lists=LISTS,
    codes=CODES,
)
ANSWER: dict[str, Any] = {
    "document": {
        "title": "Kernlehrplan für die Sekundarstufe I Physik",
        "documentType": "D1",
        "legalForm": "administrativeRegulation",
        "documentBinding": "binding",
        "lifecycle": "inForce",
        "educationSectors": ["school"],
        "regions": ["DE-NW"],
        "issuerText": "Ministerium für Schule und Bildung des Landes Nordrhein-Westfalen",
        "issuedText": "Düsseldorf, im Juni 2019",
        "validFromText": "1. August 2019",
        "editionText": "Fassung 2019",
        "evidenceBlockIds": ["p1-b1", "p1-b2"],
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
                "timeText": "Klassen 5 bis 10",
                "levelText": None,
                "institutionText": "Gymnasium",
                "targetGroupText": None,
                "evidenceBlockIds": ["p1-b1"],
            },
            "variants": [{"key": "V1", "label": "G9", "variantKind": "track"}],
        }
    ],
    "termMappings": [{"documentTerm": "Inhaltsfeld", "mapsTo": "T1", "evidenceBlockId": "p2-b1"}],
    "newTerms": [
        {"documentTerm": "Schwerpunkt", "suggestedFunction": "grouping", "evidenceBlockId": "p2-b1"}
    ],
}


def answer(**document: Any) -> dict[str, Any]:
    made = copy.deepcopy(ANSWER)
    made["document"] |= document
    return made


def rules(found: Any) -> list[tuple[str, str, str | None]]:
    return [(finding.rule, finding.severity, finding.path) for finding in found.findings]


def test_a_full_answer_is_read_into_the_document_s_values() -> None:
    profile = read_profile(ANSWER, CONTEXT)

    assert (profile.title, profile.document_type, profile.legal_form, profile.binding, profile.lifecycle) == (
        "Kernlehrplan für die Sekundarstufe I Physik",
        SCHOOL + "dt-Kernlehrplan",
        CV + "lf_administrativeRegulation",
        CV + "bind_binding",
        CV + "life_inForce",
    )
    assert (profile.issuer, profile.edition) == (
        "Ministerium für Schule und Bildung des Landes Nordrhein-Westfalen",
        "Fassung 2019",
    )
    assert (profile.issued, profile.valid_from) == ("2019-06", "2019-08-01")
    assert profile.evidence == ("p1-b1", "p1-b2")
    assert profile.findings == ()


def test_the_wording_of_dates_and_of_where_the_document_holds_is_kept_for_the_run() -> None:
    profile = read_profile(ANSWER, CONTEXT)

    assert profile.said == {
        "issuedText": "Düsseldorf, im Juni 2019",
        "validFromText": "1. August 2019",
        "regions": ["DE-NW"],
        "educationSectors": ["school"],
    }


@pytest.mark.parametrize(
    ("wording", "date"),
    [
        ("1. August 2019", "2019-08-01"),
        ("01.08.2019", "2019-08-01"),
        ("2019-08-01", "2019-08-01"),
        ("Düsseldorf, im Juni 2019", "2019-06"),
        ("08.2019", "2019-08"),
        ("2019-08", "2019-08"),
        ("Schuljahr 2019/20", "2019"),
        ("Schuljahr 2019-20", "2019"),  # no month 20: the year
        ("Ausgabe 20１９", None),  # digits of another script: none the column takes
        ("13.2019", "2019"),
        ("31.02.2019", None),  # no such day
        ("ab dem nächsten Schuljahr", None),
        (None, None),
    ],
)
def test_a_date_is_read_from_its_wording_as_far_as_it_goes(wording: str | None, date: str | None) -> None:
    assert parse_date(wording) == date


def test_specifications_with_their_variants_are_read_their_values_coded() -> None:
    [specification] = read_profile(ANSWER, CONTEXT).specifications

    assert specification == SpecificationDraft(
        key="S1",
        kind="curriculum",
        title="Physik",
        field_text="Physik",
        applicability={
            "sector": CV + "sec_school",
            "formality": CV + "form_formal",
            "timeKind": CV + "time_gradeLevel",
            "timeText": "Klassen 5 bis 10",
            "levelText": None,
            "institutionText": "Gymnasium",
            "targetGroupText": None,
        },
        evidence=("p1-b1",),
        variants=(VariantDraft("V1", "G9", CV + "var_track"),),
    )


def test_the_document_s_own_terms_are_kept_with_the_iris_they_name() -> None:
    profile = read_profile(ANSWER, CONTEXT)

    assert profile.term_mappings == (
        {"documentTerm": "Inhaltsfeld", "mapsTo": SCHOOL + "Inhaltsbereich", "evidenceBlockId": "p2-b1"},
    )
    assert profile.new_terms == (
        {"documentTerm": "Schwerpunkt", "suggestedFunction": CV + "fn_grouping", "evidenceBlockId": "p2-b1"},
    )


def test_a_key_the_lists_do_not_hold_is_a_finding_not_a_value() -> None:
    made = answer(documentType="D9")
    made["termMappings"][0]["mapsTo"] = "T7"

    profile = read_profile(made, CONTEXT)

    assert profile.document_type is None and profile.term_mappings == ()
    assert rules(profile) == [
        ("x1.unknown_key", "warning", "$.document.documentType"),
        ("x1.unknown_key", "warning", "$.termMappings[0].mapsTo"),
    ]
    assert profile.findings[0].focus_id == DOCUMENT
    assert profile.findings[0].details == {"key": "D9"}


def test_a_value_the_vocabulary_no_longer_holds_is_a_finding_not_a_value() -> None:
    profile = read_profile(answer(documentBinding="partial"), CONTEXT)

    assert profile.binding is None
    assert rules(profile) == [("x1.unknown_value", "warning", "$.document.documentBinding")]


def test_a_block_the_conversion_does_not_hold_is_a_finding_and_left_out() -> None:
    made = answer(evidenceBlockIds=["p1-b1", "p9-b9", "Seite 3"])
    made["termMappings"][0]["evidenceBlockId"] = "p8-b1"

    profile = read_profile(made, CONTEXT)

    assert profile.evidence == ("p1-b1",)
    assert profile.term_mappings[0]["evidenceBlockId"] is None
    assert rules(profile) == [
        ("x1.unknown_block", "warning", "$.document.evidenceBlockIds[1]"),
        ("x1.unknown_block", "warning", "$.document.evidenceBlockIds[2]"),
        ("x1.unknown_block", "warning", "$.termMappings[0].evidenceBlockId"),
    ]
    assert profile.findings[1].details == {"block": "Seite 3"}


def test_regions_and_sectors_other_than_the_document_s_are_findings_never_values() -> None:
    profile = read_profile(
        answer(regions=["DE-HE", "DE-NW"], educationSectors=["school", "vocational"]), CONTEXT
    )

    assert rules(profile) == [
        ("x1.regions_differ", "info", "$.document.regions"),
        ("x1.other_sectors", "info", "$.document.educationSectors"),
    ]
    assert profile.findings[0].details == {"found": ["DE-HE", "DE-NW"], "document": ["DE-NW"]}
    assert profile.findings[1].details == {"sectors": ["vocational"]}


def test_no_regions_named_differ_from_none() -> None:
    assert read_profile(answer(regions=[]), CONTEXT).findings == ()


def test_a_specification_twice_or_without_a_title_is_left_out_with_a_finding() -> None:
    made = copy.deepcopy(ANSWER)
    twice = copy.deepcopy(made["specifications"][0])
    untitled = copy.deepcopy(twice) | {"key": "S2", "title": "  "}
    made["specifications"][0]["variants"].append({"key": "V1", "label": "G8", "variantKind": "track"})
    made["specifications"] += [twice, untitled]

    profile = read_profile(made, CONTEXT)

    assert [specification.key for specification in profile.specifications] == ["S1"]
    assert [variant.label for variant in profile.specifications[0].variants] == ["G9"]
    assert rules(profile) == [
        ("x1.duplicate_key", "warning", "$.specifications[0].variants[1].key"),
        ("x1.duplicate_key", "warning", "$.specifications[1].key"),
        ("x1.blank_value", "warning", "$.specifications[2].title"),
    ]


def test_blank_wording_is_none_and_overlong_wording_is_cut_with_a_finding() -> None:
    profile = read_profile(answer(issuerText="  ", editionText="", title="T" * 1500), CONTEXT)

    assert (profile.issuer, profile.edition) == (None, None)
    assert profile.title == "T" * 1000
    assert rules(profile) == [("x1.value_cut", "info", "$.document.title")]


def test_wording_is_cut_after_its_edges_are_trimmed_so_a_cut_never_leaves_it_blank() -> None:
    made = answer(issuerText=" " * 500 + "Ministerium")
    made["specifications"][0]["title"] = "\n" * 1000 + "Physik"

    profile = read_profile(made, CONTEXT)

    assert profile.issuer == "Ministerium"
    assert profile.specifications[0].title == "Physik"
    assert profile.findings == ()


def test_a_code_left_open_is_none_without_a_finding() -> None:
    made = copy.deepcopy(ANSWER)
    made["specifications"][0]["applicability"] |= {"formality": None, "timeKind": None}

    profile = read_profile(made, CONTEXT)

    applicability = profile.specifications[0].applicability
    assert (applicability["formality"], applicability["timeKind"]) == (None, None)
    assert profile.findings == ()


def test_a_variant_of_a_kind_the_vocabulary_no_longer_holds_is_left_out_with_a_finding() -> None:
    made = copy.deepcopy(ANSWER)
    made["specifications"][0]["variants"][0]["variantKind"] = "focus"

    profile = read_profile(made, CONTEXT)

    assert profile.specifications[0].variants == ()
    assert rules(profile) == [("x1.unknown_value", "warning", "$.specifications[0].variants[0].variantKind")]
