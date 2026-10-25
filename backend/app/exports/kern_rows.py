"""A document of the first layer read for its Kern RDF (plan M1 8.3; app/exports/kern_rdf.py): the
document, its specifications and their variants, its nodes and statements, and the anchors of nodes
and statements with their blocks - rows as the tables hold them, read in one snapshot.

No visibility check: the export serves the pipeline (X5's SHACL check) of a document it already holds;
a route that exports for a reader checks what that reader sees first.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.db.documents import DocumentError
from app.vocab.lookup import REGIONS

Row = dict[str, Any]
_SNAPSHOTS = ("repeatable read", "serializable")  # the isolation levels whose queries share one snapshot

_DOCUMENT = """
SELECT d.id, d.title, d.issuer, d.edition, d.document_type_iri, d.sector_iri, d.legal_form_iri, d.binding_iri,
    d.lifecycle_iri, d.valid_from, d.valid_until, d.issued,
    ARRAY(SELECT iri FROM (
              SELECT DISTINCT ON (region) c.iri FROM unnest(d.regions) AS region JOIN vocab_concept c
                  ON c.scheme_iri = %(regions)s AND c.notation = region
              ORDER BY region, c.retired_in NULLS FIRST  -- the active concept of a notation first
          ) AS found ORDER BY iri) AS region_iris
FROM document d WHERE d.id = %(document)s
"""
_SPECIFICATIONS = """
SELECT id, spec_kind, title, field_text FROM specification WHERE document_id = %(document)s ORDER BY key
"""
_VARIANTS = """
SELECT v.id, v.specification_id, v.label, v.variant_kind_iri FROM variant v
JOIN specification s ON s.id = v.specification_id WHERE s.document_id = %(document)s ORDER BY v.key
"""
# A node lacks what every unit of it checked absent: one part of a node vouches for no other part
_NODES = """
SELECT n.id, n.parent_id, n.position, n.function_iri, n.node_type_iri, n.code, n.code_assigned,
    n.original_title, n.title_language, n.obligation_iri, n.scope_share_iri, n.extraction_depth_iri,
    n.applies_to, n.origin_iri, n.review_status_iri,
    ARRAY(SELECT point FROM extraction_unit u CROSS JOIN LATERAL unnest(u.checked_absent) AS point
          WHERE u.node_id = n.id GROUP BY point
          HAVING count(DISTINCT u.unit_key) = (SELECT count(*) FROM extraction_unit w WHERE w.node_id = n.id)
          ORDER BY point) AS checked_absent
FROM node n WHERE n.document_id = %(document)s ORDER BY n.parent_id NULLS FIRST, n.position
"""
_STATEMENTS = """
SELECT s.id, s.node_id, s.position, s.verbatim, s.language, s.lead_in, s.statement_kind_iri, s.subkind_iri,
    s.obligation_iri, s.origin_iri, s.review_status_iri, s.text_hash, s.details, s.layout_markers,
    ARRAY(SELECT a.addressee_iri FROM statement_addressee a WHERE a.statement_id = s.id
          ORDER BY a.addressee_iri) AS addressees
FROM statement s WHERE s.document_id = %(document)s ORDER BY s.node_id, s.position
"""
_ANCHORS = """
SELECT a.id, a.node_id, a.statement_id, a.page_start, a.page_end, a.printed_page, a.quote, a.match_kind_iri,
    a.match_score, a.char_start, a.char_end, a.table_cell, a.section_path,
    ARRAY(SELECT ab.block_id FROM anchor_block ab WHERE ab.anchor_id = a.id) AS blocks
FROM anchor a
WHERE a.document_id = %(document)s AND (a.node_id IS NOT NULL OR a.statement_id IS NOT NULL)
ORDER BY a.id
"""


@dataclass(frozen=True)
class KernRows:
    document: Row
    specifications: list[Row]
    variants: list[Row]
    nodes: list[Row]
    statements: list[Row]
    anchors: list[Row]  # of nodes and statements


async def read_document(connection: psycopg.AsyncConnection, document_id: UUID) -> KernRows:
    """The document's rows for its Kern RDF, in one snapshot: in a read-only transaction of its own, or
    within the caller's where that one keeps a snapshot (repeatable read, serializable) - RuntimeError
    where it does not, as a pool's connection after its first query. DocumentError where there is none."""
    if connection.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
        cursor = await connection.execute("SELECT current_setting('transaction_isolation')")
        isolation = await cursor.fetchone()
        if isolation is None or isolation[0] not in _SNAPSHOTS:
            raise RuntimeError("the Kern rows are read in one snapshot: in repeatable read, or idle")
        return await _read(connection, document_id)
    async with connection.transaction():
        await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return await _read(connection, document_id)


async def _read(connection: psycopg.AsyncConnection, document_id: UUID) -> KernRows:
    params = {"document": document_id, "regions": REGIONS}
    async with connection.cursor(row_factory=dict_row) as rows:
        await rows.execute(_DOCUMENT, params)
        document = await rows.fetchone()
        if document is None:
            raise DocumentError(f"no document {document_id}")
        read = []
        for query in (_SPECIFICATIONS, _VARIANTS, _NODES, _STATEMENTS, _ANCHORS):
            await rows.execute(query, params)
            read.append(await rows.fetchall())
    return KernRows(document, *read)
