"""A document of the first layer as Curriculum-Kern 1.0 RDF (plan M1 8.3): every row its urn:uuid, so a
SHACL focus is the row's id; exactly the triples the tables hold - nothing of the frame parts, the
profile's own terms or the anchors of the document or a specification, which the Kern has no owner for
in M1, and no wording field the Kern has no property for."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from rdflib import Graph
from rdflib.compare import graph_diff, isomorphic, to_isomorphic

from app.conversion.base import Block
from app.db.migrate import migrate
from app.db.nodes import write_subtree
from app.db.profile import write_profile
from app.domain.l1 import (
    AnchorDraft,
    NodeDraft,
    ProfileDraft,
    SpecificationDraft,
    StatementDraft,
    VariantDraft,
)
from app.domain.wording import text_hash
from app.exports.kern_rdf import kern_graph
from app.exports.kern_rows import read_document
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.document_of import document_of

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
MODEL, PROPOSED = CV + "orig_model", CV + "rev_proposed"
TEXTS = ["Kernlehrplan Physik", "1 Optik", "Die Lernenden beschreiben Licht.", "Licht breitet sich aus."]
EXPECTED = """
@prefix cur: <https://w3id.org/wlo/curriculum/core#> .
@prefix cv: <https://w3id.org/wlo/curriculum/vocab#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix land: <https://w3id.org/wlo/curriculum/region/> .
@prefix schul: <https://w3id.org/wlo/curriculum/profile/school#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<urn:uuid:{doc}> a cur:Document ;
    dct:title "Kernlehrplan Physik" ; dct:publisher "Ministerium für Schule" ; cur:edition "2. Auflage" ;
    cur:documentType schul:dt-Lehrplan ; cur:educationSector cv:sec_school ; cur:region land:DE-NW ;
    cur:legalForm cv:lf_administrativeRegulation ; cur:documentBinding cv:bind_binding ;
    cur:lifecycle cv:life_inForce ; cur:issued "2023-08"^^xsd:gYearMonth ;
    cur:validFrom "2023-08-01"^^xsd:date ;
    cur:validUntil "2030"^^xsd:gYear ; cur:represents <urn:uuid:{spec}> .
<urn:uuid:{spec}> a cur:Curriculum ; dct:title "Physik Sekundarstufe I" ; cur:fieldText "Physik" .
<urn:uuid:{variant}> a cur:Variant ; skos:prefLabel "Grundkurs" ; cur:variantKind cv:var_focus ;
    cur:variantOf <urn:uuid:{spec}> .
<urn:uuid:{root}> a cur:CurriculumNode ; cur:partOf <urn:uuid:{spec}> ; cur:nodeFunction cv:fn_area ;
    cur:nodeType schul:Inhaltsbereich ; cur:code "1" ; cur:codeAssigned false ; cur:originalTitle "Optik"@de ;
    cur:position 1 ; cur:appliesTo <urn:uuid:{variant}> ; cur:origin cv:orig_model ;
    cur:reviewStatus cv:rev_proposed ; cur:anchor <urn:uuid:{at_root}> .
<urn:uuid:{child}> a cur:CurriculumNode ; cur:partOf <urn:uuid:{root}> ; cur:nodeFunction cv:fn_grouping ;
    cur:codeAssigned false ; cur:position 1 ; cur:origin cv:orig_model ; cur:reviewStatus cv:rev_proposed .
<urn:uuid:{told}> a cur:Statement ; cur:partOf <urn:uuid:{root}> ;
    cur:verbatim "Die Lernenden beschreiben Licht."@de ; cur:leadIn "Die Lernenden"@de ;
    cur:statementKind cv:kind_learningOutcome ; cur:statementSubkind schul:Kompetenzerwartung ;
    cur:addressee cv:addr_learner ; cur:obligation cv:obl_binding ; cur:origin cv:orig_model ;
    cur:reviewStatus cv:rev_proposed ; cur:contextText "im Labor" ; cur:exampleText "mit Spiegeln"@de ;
    cur:crossCuttingMarker "BNE" ; cur:targetsContent <urn:uuid:{content}> ; cur:textHash "{told_hash}" ;
    cur:anchor <urn:uuid:{at_told}> .
<urn:uuid:{content}> a cur:Statement ; cur:partOf <urn:uuid:{root}> ;
    cur:verbatim "Licht breitet sich aus."@de ; cur:statementKind cv:kind_content ;
    cur:addressee cv:addr_learner ;
    cur:origin cv:orig_model ; cur:reviewStatus cv:rev_proposed ; cur:textHash "{content_hash}" ;
    cur:anchor <urn:uuid:{at_content}> .
<urn:uuid:{at_root}> a cur:SourceAnchor ; cur:inDocument <urn:uuid:{doc}> ; cur:pageStart 1 ;
    cur:blockId "p1-b2" ;
    cur:quote "1 Optik" ; cur:matchKind cv:match_exact .
<urn:uuid:{at_told}> a cur:SourceAnchor ; cur:inDocument <urn:uuid:{doc}> ; cur:pageStart 1 ; cur:pageEnd 1 ;
    cur:blockId "p1-b3", "p1-b4" ; cur:quote "Die Lernenden beschreiben Licht." ;
    cur:matchKind cv:match_fuzzy ;
    cur:matchScore 0.91 ; cur:charStart 0 ; cur:charEnd 32 .
<urn:uuid:{at_content}> a cur:SourceAnchor ; cur:inDocument <urn:uuid:{doc}> ; cur:printedPage "7" ;
    cur:pageStart 1 ; cur:blockId "p1-b4" .
"""


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


def block(number: int, text: str) -> Block:
    return Block(
        id=f"p1-b{number}", page=1, kind="text", text=text, bbox=(0, 0, 1, 1), font_size=10, bold=False,
        italic=False,
    )  # fmt: skip


async def one(connection: psycopg.AsyncConnection, query: str, *params: Any) -> Any:
    cursor = await connection.execute(query, params)
    [(found,)] = await cursor.fetchall()
    return found


async def a_document(connection: psycopg.AsyncConnection) -> dict[str, Any]:
    document = await document_of(connection, [block(at, text) for at, text in enumerate(TEXTS, start=1)])
    specification = SpecificationDraft(
        "S1", "curriculum", "Physik Sekundarstufe I", "Physik", {}, ("p1-b1",),
        variants=(VariantDraft("V1", "Grundkurs", CV + "var_focus"),),
    )  # fmt: skip
    profile = ProfileDraft(
        title="Kernlehrplan Physik", document_type=SCHOOL + "dt-Lehrplan",
        legal_form=CV + "lf_administrativeRegulation",
        binding=CV + "bind_binding", lifecycle=CV + "life_inForce", issuer="Ministerium für Schule",
        edition="2. Auflage", issued="2023-08", valid_from="2023-08-01", evidence=("p1-b1",),
        specifications=(specification,), term_mappings=(), new_terms=(),
    )  # fmt: skip
    specifications, _ = await write_profile(connection, document.id, profile)
    await connection.execute("UPDATE document SET valid_until = '2030' WHERE id = %s", (document.id,))
    variant = await one(connection, "SELECT id FROM variant WHERE key = 'V1'")
    told = StatementDraft(
        verbatim="Die Lernenden beschreiben Licht.", kind=CV + "kind_learningOutcome",
        addressees=(CV + "addr_learner",), origin=MODEL, review_status=PROPOSED, lead_in="Die Lernenden",
        subkind=SCHOOL + "Kompetenzerwartung", obligation=CV + "obl_binding",
        details={"contextText": "im Labor", "exampleText": "mit Spiegeln", "codeText": "K1",
                 "purposeText": "um zu sehen", "crossCuttingMarkers": ["BNE"], "targetsContent": [2]},
        anchors=(AnchorDraft(("p1-b3", "p1-b4"), page_start=1, page_end=1, quote=TEXTS[2],
                             match_kind=CV + "match_fuzzy", match_score=0.91, char_start=0, char_end=32),),
    )  # fmt: skip
    content = StatementDraft(
        verbatim=TEXTS[3], kind=CV + "kind_content", addressees=(CV + "addr_learner",), origin=MODEL,
        review_status=PROPOSED, anchors=(AnchorDraft(("p1-b4",), page_start=1, printed_page="7"),),
    )  # fmt: skip
    root = NodeDraft(
        function=CV + "fn_area", origin=MODEL, review_status=PROPOSED, node_type=SCHOOL + "Inhaltsbereich",
        code="1", original_title="Optik", applies_to=(variant,), statements=(told, content),
        anchors=(AnchorDraft(("p1-b2",), page_start=1, quote="1 Optik", match_kind=CV + "match_exact"),),
        children=(NodeDraft(function=CV + "fn_grouping", origin=MODEL, review_status=PROPOSED),),
    )  # fmt: skip
    root_id = await write_subtree(connection, document.id, root)
    ids = {
        "doc": document.id, "spec": specifications["S1"], "variant": variant, "root": root_id,
        "child": await one(connection, "SELECT id FROM node WHERE parent_id = %s", root_id),
        "told": await one(connection, "SELECT id FROM statement WHERE verbatim = %s", TEXTS[2]),
        "content": await one(connection, "SELECT id FROM statement WHERE verbatim = %s", TEXTS[3]),
    }  # fmt: skip
    ids["at_root"] = await one(connection, "SELECT id FROM anchor WHERE node_id = %s", root_id)
    for name in ("told", "content"):
        ids[f"at_{name}"] = await one(connection, "SELECT id FROM anchor WHERE statement_id = %s", ids[name])
    return ids | {"told_hash": text_hash(TEXTS[2]), "content_hash": text_hash(TEXTS[3])}


async def test_a_document_is_exactly_the_kern_graph_of_its_rows(connection: psycopg.AsyncConnection) -> None:
    ids = await a_document(connection)
    expected = Graph().parse(data=EXPECTED.format(**ids), format="turtle")

    made = kern_graph(await read_document(connection, ids["doc"]))

    if not isomorphic(made, expected):
        _, only_made, only_expected = graph_diff(to_isomorphic(made), to_isomorphic(expected))
        pytest.fail(
            f"made only:\n{only_made.serialize(format='nt')}\n"
            f"expected only:\n{only_expected.serialize(format='nt')}"
        )
    assert {"cur", "cv", "dct", "skos"} <= {prefix for prefix, _ in made.namespaces()}


async def test_a_root_node_hangs_at_the_one_specification_it_applies_to(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await document_of(connection, [block(1, TEXTS[0])])
    specifications = tuple(SpecificationDraft(key, "curriculum", key, None, {}, ()) for key in ("S1", "S2"))
    profile = ProfileDraft(
        title=None, document_type=None, legal_form=None, binding=None, lifecycle=None, issuer=None,
        edition=None, issued=None, valid_from=None, evidence=(), specifications=specifications,
        term_mappings=(), new_terms=(),
    )  # fmt: skip
    keys, _ = await write_profile(connection, document.id, profile)
    root = NodeDraft(function=CV + "fn_area", origin=MODEL, review_status=PROPOSED, applies_to=(keys["S2"],))
    root_id = await write_subtree(connection, document.id, root)

    made = kern_graph(await read_document(connection, document.id))

    assert (
        f"<urn:uuid:{root_id}> <https://w3id.org/wlo/curriculum/core#partOf> <urn:uuid:{keys['S2']}> ."
        in made.serialize(format="nt")
    )


async def test_a_root_node_hangs_at_the_document_where_it_names_no_one_specification(
    connection: psycopg.AsyncConnection,
) -> None:
    document = await document_of(connection, [block(1, TEXTS[0])])
    root_id = await write_subtree(
        connection, document.id, NodeDraft(function=CV + "fn_area", origin=MODEL, review_status=PROPOSED)
    )

    made = kern_graph(await read_document(connection, document.id))

    assert (
        f"<urn:uuid:{root_id}> <https://w3id.org/wlo/curriculum/core#partOf> <urn:uuid:{document.id}> ."
        in made.serialize(format="nt")
    )
