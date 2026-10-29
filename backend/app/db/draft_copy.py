"""A frozen document's draft copy (plan M1 9.6; Paket 9b H7): the next revision of the same edition, under
its IRI, to change what the frozen one may not.

It is a document of its own - the same source, conversion, owner, work and metadata, the revision one up,
its own draft IRI, ``copy_of`` the revision it copies - with every row the frozen one holds under ids of
its own: specifications and their variants, frame parts, nodes (``applies_to`` and their parents
followed), statements, addressees, anchors (their owner followed) and their blocks, the profile. IRIs,
origins, review statuses, revisions, positions and found anchors are taken along as they are; no run is
(``run_id`` none: the runs and their findings are the frozen revision's), so X5 owes the copy a check.
Of the latest revision of an IRI alone (``not_latest``), not of a draft (``not_frozen``), and one draft at
most is open under an IRI (``draft_open``, also the database's index).
"""

from collections.abc import Mapping
from typing import Any, Final, Literal
from uuid import UUID

import psycopg

from app.core.ids import new_id
from app.db.anchors import new_entity
from app.db.documents import DocumentError

CopyCode = Literal["not_frozen", "not_latest", "draft_open"]
# The tables whose rows are entities of their own, each with the query of the copied document's ids
_ENTITIES: Final = {
    "specification": "SELECT id FROM specification WHERE document_id = %(old)s",
    "variant": "SELECT v.id FROM variant v JOIN specification s ON s.id = v.specification_id"
    " WHERE s.document_id = %(old)s",
    "frame_part": "SELECT id FROM frame_part WHERE document_id = %(old)s",
    "node": "SELECT id FROM node WHERE document_id = %(old)s",
    "statement": "SELECT id FROM statement WHERE document_id = %(old)s",
    "anchor": "SELECT id FROM anchor WHERE document_id = %(old)s",
}
_DOCUMENT = """
INSERT INTO document (id, source_id, conversion_id, owner_id, work_id, draft_iri, iri, edition, issuer,
    revision, title, document_type_iri, sector_scheme, sector_iri, regions, legal_form_scheme,
    legal_form_iri, binding_scheme, binding_iri, lifecycle_scheme, lifecycle_iri, valid_from, valid_until,
    issued, rights_status, edited_at, copy_of)
SELECT %(new)s, source_id, conversion_id, owner_id, work_id, %(draft)s, iri, edition, issuer,
    revision + 1, title, document_type_iri, sector_scheme, sector_iri, regions, legal_form_scheme,
    legal_form_iri, binding_scheme, binding_iri, lifecycle_scheme, lifecycle_iri, valid_from, valid_until,
    issued, rights_status, now(), id
FROM document WHERE id = %(old)s
"""
# In this order: what a row names is copied before it. The profile is the frozen one's: the copy is not
# made by create_document, which would give it an empty one
_ROWS: Final = (
    """
    INSERT INTO specification (id, document_id, key, spec_kind, title, field_text, applicability)
    SELECT m.new, %(new)s, s.key, s.spec_kind, s.title, s.field_text, s.applicability
    FROM specification s JOIN copied m ON m.old = s.id WHERE s.document_id = %(old)s
    """,
    """
    INSERT INTO variant (id, specification_id, key, label, variant_kind_scheme, variant_kind_iri)
    SELECT m.new, sm.new, v.key, v.label, v.variant_kind_scheme, v.variant_kind_iri
    FROM variant v JOIN copied m ON m.old = v.id JOIN copied sm ON sm.old = v.specification_id
    """,
    """
    INSERT INTO frame_part (id, document_id, part_kind, content, origin_scheme, origin_iri,
        review_status_scheme, review_status_iri, rule_id, revision, created_at, updated_at, position)
    SELECT m.new, %(new)s, f.part_kind, f.content, f.origin_scheme, f.origin_iri,
        f.review_status_scheme, f.review_status_iri, f.rule_id, f.revision, f.created_at, f.updated_at,
        f.position
    FROM frame_part f JOIN copied m ON m.old = f.id WHERE f.document_id = %(old)s
    """,
    """
    INSERT INTO node (id, document_id, parent_id, position, function_scheme, function_iri, node_type_iri,
        code, code_assigned, original_title, title_language, obligation_scheme, obligation_iri,
        scope_share_scheme, scope_share_iri, extraction_depth_scheme, extraction_depth_iri, applies_to,
        origin_scheme, origin_iri, review_status_scheme, review_status_iri, rule_id, revision, created_at,
        updated_at, iri, statement_serial)
    SELECT m.new, %(new)s, pm.new, n.position, n.function_scheme, n.function_iri, n.node_type_iri,
        n.code, n.code_assigned, n.original_title, n.title_language, n.obligation_scheme, n.obligation_iri,
        n.scope_share_scheme, n.scope_share_iri, n.extraction_depth_scheme, n.extraction_depth_iri,
        array(SELECT am.new FROM unnest(n.applies_to) WITH ORDINALITY a (id, place)
              JOIN copied am ON am.old = a.id ORDER BY a.place),
        n.origin_scheme, n.origin_iri, n.review_status_scheme, n.review_status_iri, n.rule_id, n.revision,
        n.created_at, n.updated_at, n.iri, n.statement_serial
    FROM node n JOIN copied m ON m.old = n.id LEFT JOIN copied pm ON pm.old = n.parent_id
    WHERE n.document_id = %(old)s
    """,
    """
    INSERT INTO statement (id, document_id, node_id, position, verbatim, language, lead_in,
        statement_kind_scheme, statement_kind_iri, subkind_iri, obligation_scheme, obligation_iri,
        origin_scheme, origin_iri, review_status_scheme, review_status_iri, rule_id, text_hash, details,
        layout_markers, revision, created_at, updated_at, iri, by_hand)
    SELECT m.new, %(new)s, nm.new, s.position, s.verbatim, s.language, s.lead_in,
        s.statement_kind_scheme, s.statement_kind_iri, s.subkind_iri, s.obligation_scheme, s.obligation_iri,
        s.origin_scheme, s.origin_iri, s.review_status_scheme, s.review_status_iri, s.rule_id, s.text_hash,
        s.details, s.layout_markers, s.revision, s.created_at, s.updated_at, s.iri, s.by_hand
    FROM statement s JOIN copied m ON m.old = s.id JOIN copied nm ON nm.old = s.node_id
    WHERE s.document_id = %(old)s
    """,
    """
    INSERT INTO statement_addressee (statement_id, addressee_scheme, addressee_iri)
    SELECT sm.new, a.addressee_scheme, a.addressee_iri
    FROM statement_addressee a JOIN copied sm ON sm.old = a.statement_id
    """,
    """
    INSERT INTO anchor (id, document_id, conversion_id, node_id, statement_id, frame_part_id,
        specification_id, page_start, page_end, printed_page, quote, match_kind_scheme, match_kind_iri,
        match_score, char_start, char_end, table_cell, section_path, created_at)
    SELECT m.new, %(new)s, a.conversion_id, nm.new, sm.new, fm.new, pm.new, a.page_start, a.page_end,
        a.printed_page, a.quote, a.match_kind_scheme, a.match_kind_iri, a.match_score, a.char_start,
        a.char_end, a.table_cell, a.section_path, a.created_at
    FROM anchor a JOIN copied m ON m.old = a.id LEFT JOIN copied nm ON nm.old = a.node_id
        LEFT JOIN copied sm ON sm.old = a.statement_id LEFT JOIN copied fm ON fm.old = a.frame_part_id
        LEFT JOIN copied pm ON pm.old = a.specification_id
    WHERE a.document_id = %(old)s
    """,
    """
    INSERT INTO anchor_block (anchor_id, conversion_id, block_id)
    SELECT am.new, b.conversion_id, b.block_id FROM anchor_block b JOIN copied am ON am.old = b.anchor_id
    """,
    """
    INSERT INTO document_profile (document_id, term_mappings, new_terms, table_schemas)
    SELECT %(new)s, term_mappings, new_terms, table_schemas FROM document_profile WHERE document_id = %(old)s
    """,
)


class CopyRefused(Exception):
    """No draft copy is made: ``code`` says why, ``details`` what of it."""

    def __init__(self, code: CopyCode, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code: CopyCode = code
        self.details = dict(details or {})


async def copy_document(connection: psycopg.AsyncConnection, document_id: UUID) -> UUID:
    """The draft copy of the frozen document ``document_id``, made as above; its id. CopyRefused, or
    DocumentError for no such document, and then nothing is made."""
    async with connection.transaction():
        cursor = await connection.execute(
            "SELECT iri, revision, frozen_at IS NOT NULL FROM document WHERE id = %s", (document_id,)
        )
        found = await cursor.fetchone()
        if found is None:
            raise DocumentError(f"no document {document_id}")
        iri, revision, frozen = found
        if not frozen:
            raise CopyRefused("not_frozen", f"the document {document_id} is a draft: change it as it is")
        cursor = await connection.execute(
            "SELECT id, frozen_at IS NULL FROM document WHERE iri = %s AND revision > %s"
            " ORDER BY revision DESC",
            (iri, revision),
        )
        later = await cursor.fetchall()
        drafts = [str(row[0]) for row in later if row[1]]
        if drafts:
            raise CopyRefused("draft_open", "a draft of the IRI is open", {"document_id": drafts[0]})
        if later:
            raise CopyRefused("not_latest", f"a later revision of {iri} is frozen: copy that one")
        copy = await new_entity(connection, "document")
        try:
            async with connection.transaction():
                await connection.execute(_DOCUMENT, {"new": copy, "draft": copy.urn, "old": document_id})
        except psycopg.errors.UniqueViolation as raced:  # another copy, made meanwhile (document_one_draft)
            cursor = await connection.execute(
                "SELECT id FROM document WHERE iri = %s AND frozen_at IS NULL", (iri,)
            )
            other = await cursor.fetchone()
            details = {} if other is None else {"document_id": str(other[0])}
            raise CopyRefused("draft_open", "a draft of the IRI is open", details) from raced
        await _map(connection, document_id)
        for query in _ROWS:
            await connection.execute(query, {"new": copy, "old": document_id})
        return copy


async def _map(connection: psycopg.AsyncConnection, document_id: UUID) -> None:
    """The ids of the copied document's entities, each with a new one, in ``copied`` for the transaction."""
    await connection.execute(
        "CREATE TEMPORARY TABLE copied (old uuid PRIMARY KEY, new uuid NOT NULL) ON COMMIT DROP"
    )
    async with connection.cursor() as cursor:
        for kind, query in _ENTITIES.items():
            await cursor.execute(query, {"old": document_id})
            rows = [(old, new_id(), kind) for (old,) in await cursor.fetchall()]
            await cursor.executemany(
                "INSERT INTO entity (id, kind) VALUES (%s, %s)", [(new, made) for _, new, made in rows]
            )
            await cursor.executemany(
                "INSERT INTO copied (old, new) VALUES (%s, %s)", [(old, new) for old, new, _ in rows]
            )
