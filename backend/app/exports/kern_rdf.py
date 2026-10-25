"""A document of the first layer as Curriculum-Kern 1.0 RDF (plan M1 8.3; konzept §4, §5): the document,
its specifications and their variants, its nodes (cur:partOf the parent node, a root at its one
specification), statements and the anchors of nodes and statements, as the rows of
app/exports/kern_rows.py hold them.

Every row is ``urn:uuid:<id>`` - the draft IRI a document has until it is frozen (plan M1, IRIs) - so a
SHACL focus node is the id of the row it is about. A node lacks the docking points every unit of it
checked absent (cur:checkedAbsent). Left out in M1: the frame parts and their anchors (L2 in M3; in the
Kern they would be nodes of function fn_frame), the profile's own terms, the anchors of the document and
of specifications, and a specification's applicability.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from rdflib import RDF, SKOS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS

from app.exports.kern_rows import KernRows, Row

CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
CV = Namespace("https://w3id.org/wlo/curriculum/vocab#")
_SPECIFICATION_CLASSES = {
    "curriculum": CUR.Curriculum,
    "competencyFramework": CUR.CompetencyFramework,
    "qualificationSpecification": CUR.QualificationSpecification,
    "assessmentSpecification": CUR.AssessmentSpecification,
}
_TEXTS = ("levelText", "timeText", "contextText", "referenceMarker")  # details as written, xsd:string
_DATES = {4: XSD.gYear, 7: XSD.gYearMonth, 10: XSD.date}  # by length: YYYY, YYYY-MM, YYYY-MM-DD


def row_iri(row_id: UUID) -> URIRef:
    return URIRef(f"urn:uuid:{row_id}")


def kern_graph(rows: KernRows) -> Graph:
    """The document's Kern graph, its namespaces bound."""
    graph = Graph()
    for prefix, namespace in (("cur", CUR), ("cv", CV), ("dct", DCTERMS), ("skos", SKOS), ("xsd", XSD)):
        graph.bind(prefix, namespace)
    document = row_iri(rows.document["id"])
    specifications = [row["id"] for row in rows.specifications]
    _document(graph, rows.document, specifications)
    for specification in rows.specifications:
        _specification(graph, specification)
    for variant in rows.variants:
        _variant(graph, variant)
    for node in rows.nodes:
        _node(graph, node, _parent(node, specifications, document))
    at_place = {(row["node_id"], row["position"]): row["id"] for row in rows.statements}
    for statement in rows.statements:
        _statement(graph, statement, at_place)
    for anchor in rows.anchors:
        _anchor(graph, anchor, document)
    return graph


def _add(graph: Graph, subject: URIRef, predicate: URIRef, value: Any, **literal: Any) -> None:
    """``subject predicate value``, where there is a value: an IRI as given, else a literal."""
    if value is None:
        return
    graph.add((subject, predicate, value if isinstance(value, URIRef) else Literal(value, **literal)))


def _iri(value: str | None) -> URIRef | None:
    return None if value is None else URIRef(value)


def _date(value: str | None) -> Literal | None:
    return None if value is None else Literal(value, datatype=_DATES[len(value)])


def _document(graph: Graph, row: Row, specifications: Sequence[UUID]) -> None:
    subject = row_iri(row["id"])
    graph.add((subject, RDF.type, CUR.Document))
    _add(graph, subject, DCTERMS.title, row["title"])
    _add(graph, subject, DCTERMS.publisher, row["issuer"])
    _add(graph, subject, CUR.edition, row["edition"])
    for predicate, column in (
        (CUR.documentType, "document_type_iri"), (CUR.educationSector, "sector_iri"),
        (CUR.legalForm, "legal_form_iri"), (CUR.documentBinding, "binding_iri"),
        (CUR.lifecycle, "lifecycle_iri"),
    ):  # fmt: skip
        _add(graph, subject, predicate, _iri(row[column]))
    for region in row["region_iris"]:
        graph.add((subject, CUR.region, URIRef(region)))
    for predicate, column in (
        (CUR.issued, "issued"),
        (CUR.validFrom, "valid_from"),
        (CUR.validUntil, "valid_until"),
    ):
        _add(graph, subject, predicate, _date(row[column]))
    for specification in specifications:
        graph.add((subject, CUR.represents, row_iri(specification)))


def _specification(graph: Graph, row: Row) -> None:
    subject = row_iri(row["id"])
    graph.add((subject, RDF.type, _SPECIFICATION_CLASSES[row["spec_kind"]]))
    _add(graph, subject, DCTERMS.title, row["title"])
    _add(graph, subject, CUR.fieldText, row["field_text"])


def _variant(graph: Graph, row: Row) -> None:
    subject = row_iri(row["id"])
    graph.add((subject, RDF.type, CUR.Variant))
    _add(graph, subject, SKOS.prefLabel, row["label"])
    _add(graph, subject, CUR.variantKind, URIRef(row["variant_kind_iri"]))
    graph.add((subject, CUR.variantOf, row_iri(row["specification_id"])))


def _parent(node: Row, specifications: Sequence[UUID], document: URIRef) -> URIRef:
    """A node's parent node; a root's the one specification it applies to, else the document's one
    specification, else the document itself (cur:partOf takes all three)."""
    if node["parent_id"] is not None:
        return row_iri(node["parent_id"])
    named = [item for item in node["applies_to"] if item in specifications]
    if len(named) == 1:
        return row_iri(named[0])
    return row_iri(specifications[0]) if len(specifications) == 1 else document


def _node(graph: Graph, row: Row, parent: URIRef) -> None:
    subject = row_iri(row["id"])
    graph.add((subject, RDF.type, CUR.CurriculumNode))
    graph.add((subject, CUR.partOf, parent))
    for predicate, column in (
        (CUR.nodeFunction, "function_iri"), (CUR.nodeType, "node_type_iri"),
        (CUR.obligation, "obligation_iri"),
        (CUR.scopeShare, "scope_share_iri"), (CUR.extractionDepth, "extraction_depth_iri"),
        (CUR.origin, "origin_iri"), (CUR.reviewStatus, "review_status_iri"),
    ):  # fmt: skip
        _add(graph, subject, predicate, _iri(row[column]))
    _add(graph, subject, CUR.code, row["code"])
    _add(graph, subject, CUR.codeAssigned, row["code_assigned"])
    _add(graph, subject, CUR.originalTitle, row["original_title"], lang=row["title_language"])
    _add(graph, subject, CUR.position, row["position"])
    for applies in row["applies_to"]:
        graph.add((subject, CUR.appliesTo, row_iri(applies)))
    for point in row["checked_absent"]:
        graph.add((subject, CUR.checkedAbsent, URIRef(point)))


def _statement(graph: Graph, row: Row, at_place: Mapping[tuple[UUID, int], UUID]) -> None:
    subject = row_iri(row["id"])
    language = row["language"]
    graph.add((subject, RDF.type, CUR.Statement))
    graph.add((subject, CUR.partOf, row_iri(row["node_id"])))
    _add(graph, subject, CUR.verbatim, row["verbatim"], lang=language)
    _add(graph, subject, CUR.leadIn, row["lead_in"], lang=language)
    for predicate, column in (
        (CUR.statementKind, "statement_kind_iri"), (CUR.statementSubkind, "subkind_iri"),
        (CUR.obligation, "obligation_iri"), (CUR.origin, "origin_iri"),
        (CUR.reviewStatus, "review_status_iri"),
    ):  # fmt: skip
        _add(graph, subject, predicate, _iri(row[column]))
    for addressee in row["addressees"]:
        graph.add((subject, CUR.addressee, URIRef(addressee)))
    for marker in row["layout_markers"]:
        graph.add((subject, CUR.layoutMarker, URIRef(marker)))
    _add(graph, subject, CUR.textHash, row["text_hash"])
    details = row["details"]
    for name in _TEXTS:
        _add(graph, subject, CUR[name], details.get(name))
    _add(graph, subject, CUR.exampleText, details.get("exampleText"), lang=language)
    _add(graph, subject, CUR.purpose, details.get("purposeText"), lang=language)
    _add(graph, subject, CUR.code, details.get("codeText"))  # its number or mark as the document prints it
    for marker in details.get("crossCuttingMarkers", []):
        graph.add((subject, CUR.crossCuttingMarker, Literal(marker)))
    for position in details.get("targetsContent", []):
        if (target := at_place.get((row["node_id"], position))) is not None:
            graph.add((subject, CUR.targetsContent, row_iri(target)))


def _anchor(graph: Graph, row: Row, document: URIRef) -> None:
    subject = row_iri(row["id"])
    graph.add((row_iri(row["statement_id"] or row["node_id"]), CUR.anchor, subject))
    graph.add((subject, RDF.type, CUR.SourceAnchor))
    graph.add((subject, CUR.inDocument, document))
    for predicate, column in (
        (CUR.pageStart, "page_start"), (CUR.pageEnd, "page_end"), (CUR.printedPage, "printed_page"),
        (CUR.quote, "quote"), (CUR.charStart, "char_start"), (CUR.charEnd, "char_end"),
        (CUR.tableCell, "table_cell"), (CUR.sectionPath, "section_path"),
    ):  # fmt: skip
        _add(graph, subject, predicate, row[column])
    for block in row["blocks"]:
        graph.add((subject, CUR.blockId, Literal(block)))
    _add(graph, subject, CUR.matchKind, _iri(row["match_kind_iri"]))
    score: Decimal | None = row["match_score"]
    _add(graph, subject, CUR.matchScore, score)
