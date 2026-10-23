"""Rows the tests of the first layer's tables share (migrations l1_documents, l1_nodes, l1_anchors):
the few concepts they point at, an account's source with a finished conversion, a document."""

import re
import uuid
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.core.ids import new_id
from app.domain.wording import text_hash

CV = "https://w3id.org/wlo/curriculum/vocab#"
CUR = "https://w3id.org/wlo/curriculum/core#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
# scheme -> its concepts: (local name, types, broader)
CONCEPTS: dict[str, list[tuple[str, list[str], list[str]]]] = {
    CV + "EducationSectors": [(CV + "sec_school", [], [])],
    CV + "LegalForms": [(CV + "lf_ordinance", [], [])],
    CV + "DocumentBindings": [(CV + "bind_binding", [], [])],
    CV + "Lifecycles": [(CV + "life_inForce", [], [])],
    CV + "VariantKinds": [(CV + "var_track", [], [])],
    CV + "Stages": [(CV + "stage_X1", [], []), (CV + "stage_X4", [], [])],
    CV + "NodeFunctions": [(CV + "fn_area", [], []), (CV + "fn_unit", [], [])],
    CV + "StatementKinds": [(CV + "kind_learningOutcome", [], []), (CV + "kind_content", [], [])],
    CV + "Addressees": [(CV + "addr_learner", [], []), (CV + "addr_teacher", [], [])],
    CV + "Obligations": [(CV + "obl_mandatory", [], [])],
    CV + "Origins": [(CV + "orig_source", [], []), (CV + "orig_rule", [], []), (CV + "orig_model", [], [])],
    CV + "ReviewStatuses": [(CV + "rev_proposed", [], [])],
    CV + "ExtractionDepths": [(CV + "depth_full", [], [])],
    CV + "ScopeShares": [(CV + "share_core", [], [])],
    CV + "MatchKinds": [(CV + "match_exact", [], [])],
    CV + "LayoutMarkers": [(CV + "mark_bold", [], [])],
    SCHOOL + "NodeTypes": [(SCHOOL + "Inhaltsbereich", [CUR + "NodeType"], [CV + "fn_area"])],
    SCHOOL + "StatementSubkinds": [
        (SCHOOL + "Kompetenzerwartung", [CUR + "StatementSubkind"], [CV + "kind_learningOutcome"])
    ],
    SCHOOL + "DocumentTypes": [(SCHOOL + "dt-Lehrplan", [CUR + "DocumentType"], [])],
}


def seed_vocabulary(connection: psycopg.Connection) -> None:
    """The concepts the tables point at, as app.vocab.load would leave them, cut to these few."""
    for scheme, concepts in CONCEPTS.items():
        connection.execute(
            "INSERT INTO vocab_scheme (iri, types, pref_labels, properties) VALUES (%s, '{}', '{}', '{}')",
            (scheme,),
        )
        for iri, types, broader in concepts:
            connection.execute(
                "INSERT INTO vocab_concept (iri, scheme_iri, types, pref_labels, alt_labels, definitions,"
                " broader, properties) VALUES (%s, %s, %s, '{}', '{}', '{}', %s, '{}')",
                (iri, scheme, types, broader),
            )


def add_entity(connection: psycopg.Connection, kind: str) -> uuid.UUID:
    made = new_id()
    connection.execute("INSERT INTO entity (id, kind) VALUES (%s, %s)", (made, kind))
    return made


def add_conversion(connection: psycopg.Connection, digest: bytes = b"\x01" * 32) -> dict[str, uuid.UUID]:
    """An account, its source with a file, and that file's finished conversion with a block p1-b1."""
    owner = new_id()
    # a UUIDv7 begins with its time: its random end tells two made at once apart
    connection.execute("INSERT INTO account (id, name) VALUES (%s, %s)", (owner, f"konto-{owner.hex[-12:]}"))
    file_id = new_id()
    connection.execute(
        "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 1, %s)",
        (file_id, digest, f"sources/{digest.hex()}"),
    )
    source = add_entity(connection, "source")
    connection.execute(
        "INSERT INTO source (id, owner_id, provenance, register_status, file_id, file_name, mime)"
        " VALUES (%s, %s, 'upload', 'acquired', %s, 'plan.pdf', 'application/pdf')",
        (source, owner, file_id),
    )
    conversion = add_entity(connection, "conversion")
    connection.execute(
        "INSERT INTO conversion (id, source_file_id, engine, engine_version, status, pages, printed_pages,"
        " markdown, finished_at) VALUES (%s, %s, 'pdfplumber', '0.11.10', 'done', 2, %s, '', now())",
        (conversion, file_id, Jsonb([None, None])),
    )
    for page, block in ((1, "p1-b1"), (2, "p2-b1")):
        connection.execute(
            "INSERT INTO document_block (conversion_id, block_id, page, last_page, seq, kind, text,"
            " x0, top, x1, bottom, bold, italic)"
            " VALUES (%s, %s, %s, %s, %s, 'text', 'Text', 0, 0, 1, 1, false, false)",
            (conversion, block, page, page, page),
        )
    return {"owner": owner, "source": source, "conversion": conversion}


def add_document(connection: psycopg.Connection, made: dict[str, uuid.UUID], **columns: Any) -> uuid.UUID:
    """A document of the conversion's source, in the school sector, with ``columns`` beside."""
    document = add_entity(connection, "document")
    values = {
        "source_id": made["source"],
        "conversion_id": made["conversion"],
        "owner_id": made["owner"],
        "draft_iri": document.urn,
        "sector_scheme": CV + "EducationSectors",
        "sector_iri": CV + "sec_school",
    } | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO document (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the tests' own names
        (document, *values.values()),
    )
    return document


def add_node(
    connection: psycopg.Connection,
    document: uuid.UUID,
    parent: uuid.UUID | None = None,
    position: int = 1,
    **columns: Any,
) -> uuid.UUID:
    """A node of the document, an area from the source, proposed."""
    node = add_entity(connection, "node")
    values = {
        "document_id": document,
        "parent_id": parent,
        "position": position,
        "function_scheme": CV + "NodeFunctions",
        "function_iri": CV + "fn_area",
        "origin_scheme": CV + "Origins",
        "origin_iri": CV + "orig_source",
        "review_status_scheme": CV + "ReviewStatuses",
        "review_status_iri": CV + "rev_proposed",
    } | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO node (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the tests' own names
        (node, *values.values()),
    )
    return node


def add_statement(
    connection: psycopg.Connection,
    document: uuid.UUID,
    node: uuid.UUID,
    *,
    addressees: tuple[str, ...] = ("addr_learner",),
    anchors: int = 1,
    position: int = 1,
    **columns: Any,
) -> uuid.UUID:
    """A learning outcome at the node with its addressees and as many anchors on page 1 as
    ``anchors`` says, written in one transaction."""
    statement = add_entity(connection, "statement")
    verbatim = columns.pop("verbatim", "Die Lernenden planen ihre Arbeit.")
    values = {
        "document_id": document,
        "node_id": node,
        "position": position,
        "verbatim": verbatim,
        "statement_kind_scheme": CV + "StatementKinds",
        "statement_kind_iri": CV + "kind_learningOutcome",
        "origin_scheme": CV + "Origins",
        "origin_iri": CV + "orig_source",
        "review_status_scheme": CV + "ReviewStatuses",
        "review_status_iri": CV + "rev_proposed",
        "text_hash": text_hash(verbatim),
    } | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    with connection.transaction():
        connection.execute(
            f"INSERT INTO statement (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the tests' own names
            (statement, *values.values()),
        )
        for addressee in addressees:
            connection.execute(
                "INSERT INTO statement_addressee (statement_id, addressee_scheme, addressee_iri)"
                " VALUES (%s, %s, %s)",
                (statement, CV + "Addressees", CV + addressee),
            )
        for _ in range(anchors):
            connection.execute(
                "INSERT INTO anchor (id, document_id, conversion_id, statement_id, page_start)"
                " SELECT %s, id, conversion_id, %s, 1 FROM document WHERE id = %s",
                (add_entity(connection, "anchor"), statement, values["document_id"]),
            )
    return statement


def add_specification(
    connection: psycopg.Connection, document: uuid.UUID, key: str = "s1", **columns: Any
) -> uuid.UUID:
    """A curriculum the document stands for, named by ``key`` within it."""
    specification = add_entity(connection, "specification")
    values = {"document_id": document, "key": key, "spec_kind": "curriculum", "title": "Mathematik"} | columns
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    connection.execute(
        f"INSERT INTO specification (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the tests' own names
        (specification, *values.values()),
    )
    return specification


def add_variant(connection: psycopg.Connection, specification: uuid.UUID, key: str = "v1") -> uuid.UUID:
    """A track of the specification, named by ``key`` within it."""
    variant = add_entity(connection, "variant")
    connection.execute(
        "INSERT INTO variant (id, specification_id, key, label, variant_kind_scheme, variant_kind_iri)"
        " VALUES (%s, %s, %s, 'Gymnasium', %s, %s)",
        (variant, specification, key, CV + "VariantKinds", CV + "var_track"),
    )
    return variant


def add_run(connection: psycopg.Connection, document: uuid.UUID, stage: str = "stage_X4") -> uuid.UUID:
    """A run of a stage of the pipeline on the document."""
    run = add_entity(connection, "extraction_run")
    connection.execute(
        "INSERT INTO extraction_run (id, document_id, stage_scheme, stage_iri) VALUES (%s, %s, %s, %s)",
        (run, document, CV + "Stages", CV + stage),
    )
    return run


def listed_values(connection: psycopg.Connection, table: str, column: str) -> set[str]:
    """The values the CHECK of a column lists, as the database reads it back."""
    found = connection.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s",
        (table, f"{table}_{column}_check"),
    ).fetchone()
    assert found is not None, f"no CHECK on {table}.{column}"
    return set(re.findall(r"'([^']*)'::text", found[0]))
