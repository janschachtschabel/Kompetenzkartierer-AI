"""The tables of what a document is and what it stands for (migration l1_documents, plan M1 4.2):
work, document and its profile, specifications with their variants, extraction runs."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, get_args

import psycopg
import pytest
from psycopg import errors

from app.db.migrate import migrate
from app.domain.l1 import SpecificationKind
from app.sources.register import RightsStatus
from tests.db.l1 import (
    CV,
    SCHOOL,
    add_conversion,
    add_document,
    add_entity,
    add_specification,
    listed_values,
    seed_vocabulary,
)

pytestmark = pytest.mark.pg

SCHEMAS = Path(__file__).resolve().parents[3] / "ontology" / "schemas"


@pytest.fixture
def connection(database_url: str) -> Iterator[psycopg.Connection]:
    migrate(database_url)
    with psycopg.connect(database_url, autocommit=True) as opened:
        seed_vocabulary(opened)
        yield opened


@pytest.fixture
def made(connection: psycopg.Connection) -> dict[str, Any]:
    return add_conversion(connection)


def test_a_new_document_is_a_first_unfrozen_revision_of_unclear_rights(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    document = add_document(connection, made)

    row = connection.execute(
        "SELECT revision, frozen_at, iri, rights_status, regions, title FROM document WHERE id = %s",
        (document,),
    ).fetchone()

    assert row == (1, None, None, "unklar", [], None)


@pytest.mark.parametrize(
    "columns",
    [
        {"regions": ["NRW"]},
        {"regions": ["DE-NW", "de-by"]},
        {"regions": ["DE-NW", None]},
        {"title": "\N{IDEOGRAPHIC SPACE}\N{NO-BREAK SPACE}"},
        {"valid_from": "1. August 2023"},
        {"issued": "2023-8"},
        {"revision": 0},
        {"draft_iri": "https://example.org/doc/1"},
        {"draft_iri": "urn:uuid:01a16940-29e3-7bf4-86d3-421b72698f8e"},  # another id's
        {"frozen_at": "2026-10-23T12:00:00Z"},  # frozen, yet without its IRI
        {"legal_form_scheme": CV + "LegalForms"},  # a scheme without its value
        {"rights_status": "frei"},
        {"issuer": " "},
        {"document_type_iri": CV + "sec_school"},  # a concept, but no document type
    ],
    ids=[
        "region-code",
        "region-case",
        "region-null",
        "title-of-space",
        "valid-from",
        "issued",
        "revision",
        "draft-iri",
        "draft-iri-of-another",
        "frozen",
        "pair",
        "rights",
        "issuer",
        "no-document-type",
    ],
)
def test_a_document_s_values_keep_their_forms(
    connection: psycopg.Connection, made: dict[str, Any], columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_document(connection, made, **columns)


def test_one_iri_names_each_revision_of_a_document_once(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    # a draft copy is a new revision of the same edition, with the same IRIs (plan M1 9.6)
    iri = "https://example.org/kk/doc/msb-nrw/klp-mathematik/2019"
    frozen = {"iri": iri, "frozen_at": "2026-10-23T12:00:00Z"}
    add_document(connection, made, revision=1, document_type_iri=SCHOOL + "dt-Lehrplan", **frozen)
    add_document(connection, made, revision=2, iri=iri)

    with pytest.raises(errors.UniqueViolation):
        add_document(connection, made, revision=2, iri=iri)


def test_a_document_s_dates_and_regions_are_held_as_the_document_gives_them(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    document = add_document(
        connection,
        made,
        regions=["DE-BE", "DE-BB"],
        valid_from="2023-08-01",
        issued="2023-06",
        valid_until="2030",
    )

    row = connection.execute(
        "SELECT regions, valid_from, issued, valid_until FROM document WHERE id = %s", (document,)
    )

    assert row.fetchone() == (["DE-BE", "DE-BB"], "2023-08-01", "2023-06", "2030")


@pytest.mark.parametrize(
    "columns",
    [
        {"sector_iri": CV + "stage_X1"},  # a concept of another scheme
        {"document_type_iri": SCHOOL + "dt-Nirgends"},
        {"legal_form_scheme": CV + "LegalForms", "legal_form_iri": CV + "bind_binding"},
    ],
    ids=["sector", "document-type", "legal-form"],
)
def test_a_document_s_values_are_concepts_of_their_schemes(
    connection: psycopg.Connection, made: dict[str, Any], columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.ForeignKeyViolation):
        add_document(connection, made, **columns)


def test_the_rights_a_document_may_have_are_those_the_code_knows(connection: psycopg.Connection) -> None:
    assert listed_values(connection, "document", "rights_status") == set(get_args(RightsStatus))


def test_a_specification_s_kinds_are_those_x1_names(connection: psycopg.Connection) -> None:
    schema = json.loads((SCHEMAS / "x1-dokumentprofil.schema.json").read_text(encoding="utf-8"))
    named = schema["properties"]["specifications"]["items"]["properties"]["kind"]["enum"]

    assert (
        listed_values(connection, "specification", "spec_kind")
        == set(get_args(SpecificationKind))
        == set(named)
    )


def test_a_document_names_each_of_its_specifications_by_a_key_of_its_own(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    document = add_document(connection, made)
    add_specification(connection, document)
    add_specification(connection, add_document(connection, made))  # another's key is its own

    with pytest.raises(errors.UniqueViolation):
        add_specification(connection, document)
    with pytest.raises(errors.NotNullViolation):
        add_specification(connection, document, key="s2", document_id=None)  # what no document stands for


def test_a_variant_of_a_specification_is_of_a_kind_and_named_once(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    specification = add_specification(connection, add_document(connection, made))
    variant = (CV + "VariantKinds", CV + "var_track")

    def add_variant(key: str, kind: tuple[str, str] = variant) -> None:
        connection.execute(
            "INSERT INTO variant (id, specification_id, key, label, variant_kind_scheme, variant_kind_iri)"
            " VALUES (%s, %s, %s, 'Gymnasium', %s, %s)",
            (add_entity(connection, "variant"), specification, key, *kind),
        )

    add_variant("v1")
    with pytest.raises(errors.UniqueViolation):
        add_variant("v1")
    with pytest.raises(errors.ForeignKeyViolation):
        add_variant("v2", (CV + "VariantKinds", CV + "sec_school"))


@pytest.mark.parametrize(
    "columns",
    [{"spec_kind": "lehrplan"}, {"title": " "}],
    ids=["kind", "title"],
)
def test_a_specification_has_a_kind_and_a_title(
    connection: psycopg.Connection, made: dict[str, Any], columns: dict[str, Any]
) -> None:
    with pytest.raises(errors.CheckViolation):
        add_specification(connection, add_document(connection, made), **columns)


def test_a_run_names_its_stage_and_ends_after_it_began(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    document = add_document(connection, made)

    def add_run(stage: str, **columns: Any) -> None:
        values = {"document_id": document, "stage_scheme": CV + "Stages", "stage_iri": stage} | columns
        names = ", ".join(values)
        marks = ", ".join(["%s"] * len(values))
        connection.execute(
            f"INSERT INTO extraction_run (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the tests' names
            (add_entity(connection, "extraction_run"), *values.values()),
        )

    add_run(CV + "stage_X1", model="gpt-6-luna", prompt_version="x1@1")
    with pytest.raises(errors.ForeignKeyViolation):
        add_run(CV + "sec_school")
    with pytest.raises(errors.CheckViolation):
        add_run(CV + "stage_X1", started_at="2026-10-23T12:00:00Z", finished_at="2026-10-23T11:00:00Z")


def test_a_work_has_a_title_and_one_iri_names_one_work(connection: psycopg.Connection) -> None:
    def add_work(title: str, iri: str | None = None) -> None:
        connection.execute(
            "INSERT INTO work (id, title, iri) VALUES (%s, %s, %s)",
            (add_entity(connection, "work"), title, iri),
        )

    add_work("Kernlehrplan Mathematik", "https://example.org/kk/work/de-nw/klp-mathematik")
    with pytest.raises(errors.UniqueViolation):
        add_work("Kernlehrplan Mathematik", "https://example.org/kk/work/de-nw/klp-mathematik")
    with pytest.raises(errors.CheckViolation):
        add_work("  ")


def test_a_document_has_a_profile_row_of_its_own_with_empty_lists(
    connection: psycopg.Connection, made: dict[str, Any]
) -> None:
    document = add_document(connection, made)
    connection.execute("INSERT INTO document_profile (document_id) VALUES (%s)", (document,))

    row = connection.execute(
        "SELECT term_mappings, new_terms, table_schemas FROM document_profile WHERE document_id = %s",
        (document,),
    ).fetchone()

    assert row == ([], [], [])
    with pytest.raises(errors.CheckViolation):
        connection.execute(
            "UPDATE document_profile SET term_mappings = '{}' WHERE document_id = %s", (document,)
        )
