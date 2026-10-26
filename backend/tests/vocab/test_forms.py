"""The editor's form schema (plan M1 9.1, Paket 9 G10): the fields of a node and of a statement, each
no laxer than the core's shapes demand, with the active values of their lists - a profile's node types
and subkinds with label, definition, note and examples."""

from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from rdflib import Graph, Namespace, URIRef

from app.db.migrate import migrate
from app.domain.l1 import WORDING_FIELDS
from app.vocab.forms import NODE_FIELDS, STATEMENT_FIELDS, FormField, form_of
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
SH = Namespace("http://www.w3.org/ns/shacl#")
CUR = Namespace("https://w3id.org/wlo/curriculum/core#")
SHS = Namespace("https://w3id.org/wlo/curriculum/shapes#")


def shape_counts(shapes: Graph, shape: URIRef) -> dict[str, tuple[int, int | None]]:
    """The cardinality the shape demands of each property, where a violation follows from it."""
    found: dict[str, tuple[int, int | None]] = {}
    for prop in shapes.objects(shape, SH.property):
        if shapes.value(prop, SH.severity) not in (None, SH.Violation):
            continue  # a warning asks, it does not demand
        path = shapes.value(prop, SH.path)
        least, most = shapes.value(prop, SH.minCount), shapes.value(prop, SH.maxCount)
        found["cur:" + str(path).removeprefix(str(CUR))] = (
            0 if least is None else int(str(least)),
            None if most is None else int(str(most)),
        )
    return found


@pytest.mark.parametrize(
    ("shape", "fields"),
    [("CurriculumNodeShape", NODE_FIELDS), ("StatementShape", STATEMENT_FIELDS)],
    ids=["node", "statement"],
)
def test_a_field_is_no_laxer_than_the_shapes_demand(shape: str, fields: tuple[FormField, ...]) -> None:
    shapes = Graph().parse(ONTOLOGY / "ontologie" / "cur-shapes.ttl", format="turtle")
    counts = shape_counts(shapes, SHS[shape])

    checked = [(field, field.path) for field in fields if field.path is not None]
    assert checked  # the shapes know most of them
    for field, path in checked:
        least, most = counts[path]  # a field's path is one the shape names
        assert field.required or least == 0, field.key
        assert not field.many or most is None, field.key


def test_a_statement_offers_its_wording_fields_as_texts() -> None:
    offered = {field.key: field for field in STATEMENT_FIELDS}

    for name in WORDING_FIELDS:
        assert (offered[name].kind, offered[name].required, offered[name].many) == ("text", False, False)
    assert offered["verbatim"].kind == "longtext" and offered["verbatim"].required
    assert offered["addressees"].many and offered["addressees"].required


@pytest.fixture
async def connection(database_url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as opened:
        yield opened


@pytest.mark.pg
@pytest.mark.anyio
async def test_a_profile_s_form_offers_its_active_values_with_their_texts(
    connection: psycopg.AsyncConnection,
) -> None:
    await connection.execute(
        "UPDATE vocab_concept SET retired_in = 1 WHERE iri = ANY(%s)",
        ([SCHOOL + "Inhaltsbereich", CV + "addr_family"],),
    )

    form = await form_of(connection, "school")

    assert form is not None and form.sector == "school" and form.profile == SCHOOL + "Terminology"
    offered = {key: [value.iri for value in values] for key, values in form.values.items()}
    assert len(offered["node_type"]) == 9  # the school's ten node types but the retired one
    assert SCHOOL + "Inhaltsbereich" not in offered["node_type"]
    assert len(offered["subkind"]) == 13 and len(offered["statement_kind"]) == 8
    assert len(offered["function"]) == 7 and len(offered["obligation"]) == 8
    assert CV + "addr_family" not in offered["addressees"] and len(offered["addressees"]) == 5
    staged = next(value for value in form.values["node_type"] if value.iri == SCHOOL + "Stufenabschnitt")
    assert (staged.label, staged.broader) == ("Stufenabschnitt", (CV + "fn_grouping",))
    assert staged.examples and staged.definition and staged.delimitation
    labels = [value.label for value in form.values["function"]]
    assert labels == sorted(labels, key=str.casefold)  # in the order of their labels
    assert set(form.values) == {
        field.key for field in (*NODE_FIELDS, *STATEMENT_FIELDS) if field.kind in ("concept", "concepts")
    }


@pytest.mark.pg
@pytest.mark.anyio
async def test_a_sector_without_a_profile_has_no_form(connection: psycopg.AsyncConnection) -> None:
    assert await form_of(connection, "kindergarten") is None
