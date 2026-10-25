"""X5's SHACL gate (plan M1 8.4; konzept §14): the shapes of cur-shapes.ttl and profil-shapes.ttl, no
inference, the model in the data graph - as ontology/pruefung/pruefe.py checks the examples - over a
document's Kern graph, in a child process with a deadline. The model left without the lexicons,
alignments and migration, the document's rows as focus nodes and rdflib's queries kept translated: a
measured tenth of the time, the same results (plan M1, Nachtrag 8a)."""

import multiprocessing
import uuid
from pathlib import Path

import pytest
from pyshacl import validate
from rdflib import RDF, BNode, Graph, Namespace
from rdflib.plugins.sparql import parser, processor

from app.core.child import ChildLog
from app.exports.kern_rdf import kern_graph
from app.exports.kern_rows import KernRows
from app.pipeline.shacl import ShaclCrashed, ShaclTimeout, as_findings, shacl_check
from app.pipeline.shacl_child import ShaclResult, validate_graph

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
EXAMPLES = ONTOLOGY / "beispiele"
EX = Namespace("https://w3id.org/wlo/curriculum/example/")
SH = Namespace("http://www.w3.org/ns/shacl#")
SHAPES = "https://w3id.org/wlo/curriculum/shapes#"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
TOLD = ChildLog(level="WARNING", format="text", request_id="-")
pytestmark = pytest.mark.anyio


def example(name: str) -> Graph:
    return Graph().parse(EXAMPLES / name, format="turtle")


def broken(results: list[ShaclResult]) -> set[tuple[str, str]]:
    return {(found.focus, found.shape) for found in results if found.severity == "violation"}


def test_the_faulty_example_breaks_every_shape_it_says_it_breaks() -> None:
    data = example("fehlerhaft.ttl")
    expected = {
        (str(focus), str(shape).removeprefix(SHAPES))
        for case in data.subjects(EX.expectsViolationOf, None)
        for shape in data.objects(case, EX.expectsViolationOf)
        for focus in data.objects(case, EX.focus)
    }

    found = broken(validate_graph(ONTOLOGY, data))

    assert expected and expected <= found


def test_a_sound_example_breaks_no_shape() -> None:
    assert broken(validate_graph(ONTOLOGY, example("ohm-kette.ttl"))) == set()


def test_each_query_is_parsed_once_however_many_rows_it_meets_and_rdflib_is_left_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed: list[str] = []
    real = parser.parseQuery

    def counted(text: str) -> object:
        parsed.append(text)
        return real(text)

    monkeypatch.setattr(parser, "parseQuery", counted)
    asked = processor.SPARQLProcessor.query

    validate_graph(ONTOLOGY, example("ohm-kette.ttl"))  # 75 rows, each met by several SPARQL constraints

    assert parsed and len(parsed) == len(set(parsed))
    assert processor.SPARQLProcessor.query is asked


def _whole_model() -> Graph:
    model = Graph()
    for folder in ("ontologie", "vokabulare", "profile"):
        for path in sorted((ONTOLOGY / folder).glob("*.ttl")):
            model.parse(path, format="turtle")
    return model


def whole_and_chosen(data: Graph) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]]]:
    """The results on the data's rows of V1 as pruefe.py runs it - the whole model, every node a focus,
    no query kept - and of the variant X5 runs."""
    shapes = Graph()
    for path in (ONTOLOGY / "ontologie" / "cur-shapes.ttl", ONTOLOGY / "profile" / "profil-shapes.ttl"):
        shapes.parse(path, format="turtle")
    _, report, _ = validate(
        _whole_model() + data, shacl_graph=shapes, inference="none", advanced=True, allow_warnings=True,
        meta_shacl=False,
    )  # fmt: skip
    subjects = {str(subject) for subject in data.subjects(RDF.type, None)}
    whole = set()
    for result in report.subjects(RDF.type, SH.ValidationResult):
        shape = report.value(result, SH.sourceShape)
        if isinstance(shape, BNode):
            shape = shapes.value(None, SH.property, shape)
        focus = str(report.value(result, SH.focusNode))
        severity = str(report.value(result, SH.resultSeverity)).removeprefix(str(SH)).lower()
        if focus in subjects:
            whole.add((focus, str(shape).removeprefix(SHAPES), severity))
    chosen = {(found.focus, found.shape, found.severity) for found in validate_graph(ONTOLOGY, data)}
    return whole, chosen


@pytest.mark.parametrize("name", sorted(path.name for path in EXAMPLES.glob("*.ttl")))
def test_the_chosen_model_with_kept_queries_finds_what_the_whole_model_finds(name: str) -> None:
    whole, chosen = whole_and_chosen(example(name))

    assert chosen == whole
    assert whole or not name.startswith("fehlerhaft")  # a faulty example faults


def a_document(addressees: list[str]) -> KernRows:
    """A school document of one node and one statement, as the export reads it."""
    document, specification, node, statement = (uuid.uuid4() for _ in range(4))
    return KernRows(
        {"id": document, "title": "Plan", "issuer": None, "edition": None,
         "document_type_iri": SCHOOL + "dt-Lehrplan", "sector_iri": CV + "sec_school", "legal_form_iri": None,
         "binding_iri": None, "lifecycle_iri": None, "valid_from": None, "valid_until": None, "issued": None,
         "region_iris": []},
        [{"id": specification, "spec_kind": "curriculum", "title": "Physik", "field_text": "Physik"}],
        [],
        [{"id": node, "parent_id": None, "position": 1, "function_iri": CV + "fn_area",
          "node_type_iri": SCHOOL + "Inhaltsbereich", "code": "1", "code_assigned": False,
          "original_title": "Optik", "title_language": "de", "obligation_iri": None, "scope_share_iri": None,
          "extraction_depth_iri": None, "applies_to": [], "origin_iri": CV + "orig_model",
          "review_status_iri": CV + "rev_proposed", "checked_absent": []}],
        [{"id": statement, "node_id": node, "position": 1, "verbatim": "Die Lernenden beschreiben Licht.",
          "language": "de", "lead_in": None, "statement_kind_iri": CV + "kind_content", "subkind_iri": None,
          "obligation_iri": None, "origin_iri": CV + "orig_model", "review_status_iri": CV + "rev_proposed",
          "text_hash": "x", "details": {}, "layout_markers": [], "addressees": addressees}],
        [{"id": uuid.uuid4(), "node_id": None, "statement_id": statement, "page_start": 1, "page_end": None,
          "printed_page": None, "quote": None, "match_kind_iri": None, "match_score": None,
          "char_start": None, "char_end": None, "table_cell": None, "section_path": None,
          "blocks": ["p1-b2"]}],
    )  # fmt: skip


async def test_a_document_is_checked_in_a_child_and_its_findings_name_its_rows() -> None:
    rows = a_document(addressees=[])  # a statement needs an addressee (StatementShape)
    [statement] = rows.statements

    results = await shacl_check(kern_graph(rows), ontology_dir=ONTOLOGY, timeout_s=120, told=TOLD)
    findings = as_findings(results, rows.document["id"])

    assert ("shacl.StatementShape", "violation", statement["id"], "cur:addressee") in {
        (found.rule, found.severity, found.focus_id, found.path) for found in findings
    }


async def test_a_sound_document_has_no_violation() -> None:
    results = await shacl_check(
        kern_graph(a_document([CV + "addr_learner"])), ontology_dir=ONTOLOGY, timeout_s=120, told=TOLD
    )

    assert [found for found in results if found.severity == "violation"] == []


def test_a_finding_focused_outside_the_rows_is_the_document_s() -> None:
    document, statement = uuid.uuid4(), uuid.uuid4()
    outside = CV + "kind_content"
    results = [
        ShaclResult(
            f"urn:uuid:{statement}", "StatementShape", "violation", "cur:addressee", "Kein Adressat.", None,
            "MinCountConstraintComponent",
        ),
        ShaclResult(outside, "ConceptLabelShape", "warning", None, "Ohne Label.", "x", None),
        ShaclResult(f"urn:uuid:{statement}", "StatementShape", "info", None, "", None, None),  # no message
    ]  # fmt: skip

    findings = as_findings(results, document)

    seen = [
        (found.rule, found.severity, found.focus_id, found.path, found.message, found.details)
        for found in findings
    ]
    assert seen == [
        ("shacl.StatementShape", "violation", statement, "cur:addressee", "Kein Adressat.",
         {"component": "MinCountConstraintComponent"}),
        ("shacl.ConceptLabelShape", "warning", document, None, "Ohne Label.",
         {"focus": "https://w3id.org/wlo/curriculum/vocab#kind_content", "value": "x"}),
        ("shacl.StatementShape", "info", statement, None, "StatementShape", {}),  # a finding says something
    ]  # fmt: skip


async def test_a_check_past_its_deadline_is_given_up_and_its_child_ended() -> None:
    with pytest.raises(ShaclTimeout):
        await shacl_check(kern_graph(a_document([])), ontology_dir=ONTOLOGY, timeout_s=0.05, told=TOLD)

    assert multiprocessing.active_children() == []


async def test_a_check_that_breaks_in_its_child_comes_back_by_its_kind(tmp_path: Path) -> None:
    # the shapes are missing: rdflib reads the path, and its error's kind comes back, never its text
    with pytest.raises(ShaclCrashed, match=r"^the SHACL validation raised \w+ in its process$"):
        await shacl_check(kern_graph(a_document([])), ontology_dir=tmp_path, timeout_s=120, told=TOLD)


def test_the_chosen_model_finds_on_an_exported_document_what_the_whole_model_finds() -> None:
    whole, chosen = whole_and_chosen(kern_graph(a_document(addressees=[])))

    assert whole and chosen == whole
