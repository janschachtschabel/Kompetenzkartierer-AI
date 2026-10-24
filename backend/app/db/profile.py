"""A document's profile as X1 read it (plan M1 6.2), written to the first layer: the document's own
values, the terms of its own (document_profile), its specifications with their variants, and an
anchor at the blocks each was read from - the document's naming none of its rows (0015).

A document type set before X1 - by the editor - stays: X1 reading another is a finding, never a
change. The regions and the sector are the document's from when it was made and are not written
here. A work is never set from X1: one of the same title and region is only suggested (plan M1
6.2, the editors set works, 9.6). Written as one, within the caller's transaction where it has one:
X1 writes its stage at once (plan M1 6, Festlegung 1).
"""

from collections.abc import Sequence
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.db.anchors import CV, new_entity, write_anchor
from app.db.documents import DocumentError
from app.db.findings import Finding
from app.db.runs import done_stages
from app.domain.l1 import AnchorDraft, ProfileDraft

_VALUES = """
UPDATE document SET title = %(title)s, document_type_iri = coalesce(document_type_iri, %(type)s),
    legal_form_scheme = %(legal_scheme)s, legal_form_iri = %(legal)s, binding_scheme = %(binding_scheme)s,
    binding_iri = %(binding)s, lifecycle_scheme = %(lifecycle_scheme)s, lifecycle_iri = %(lifecycle)s,
    issuer = %(issuer)s, edition = %(edition)s, issued = %(issued)s, valid_from = %(valid_from)s,
    updated_at = now()
WHERE id = %(id)s
"""
_SPECIFICATION = """
INSERT INTO specification (id, document_id, key, spec_kind, title, field_text, applicability)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""
_VARIANT = """
INSERT INTO variant (id, specification_id, key, label, variant_kind_scheme, variant_kind_iri)
VALUES (%s, %s, %s, %s, %s, %s)
"""
# a title as works and documents are compared: in one case, its spaces one
_SAME_TITLE = "lower(regexp_replace(btrim({}), '\\s+', ' ', 'g'))"
_WORK = f"""
SELECT id FROM work WHERE region = ANY (%s) AND {_SAME_TITLE.format("title")} = {_SAME_TITLE.format("%s")}
ORDER BY created_at, id LIMIT 1
"""  # noqa: S608 - fixed parts


async def write_profile(
    connection: psycopg.AsyncConnection, document_id: UUID, draft: ProfileDraft
) -> tuple[dict[str, UUID], list[Finding]]:
    """Write the profile to the document; the ids of its specifications by their keys (S1 …), and
    the findings of the writing. DocumentError for a document that is none."""
    async with connection.transaction():
        cursor = await connection.execute(
            "SELECT conversion_id, document_type_iri FROM document WHERE id = %s FOR NO KEY UPDATE",
            (document_id,),
        )
        found = await cursor.fetchone()
        if found is None:
            raise DocumentError(f"no document {document_id}")
        conversion_id, document_type = found
        notes: list[Finding] = []
        if document_type is not None and draft.document_type not in (None, document_type):
            notes.append(
                Finding(
                    "x1.document_type_differs",
                    "info",
                    document_id,
                    "the document reads as of another document type than it was given",
                    "$.document.documentType",
                    {"found": draft.document_type, "document": document_type},
                )
            )
        await connection.execute(
            _VALUES,
            {
                "id": document_id,
                "title": draft.title,
                "type": draft.document_type,
                "legal_scheme": _scheme("LegalForms", draft.legal_form),
                "legal": draft.legal_form,
                "binding_scheme": _scheme("DocumentBindings", draft.binding),
                "binding": draft.binding,
                "lifecycle_scheme": _scheme("Lifecycles", draft.lifecycle),
                "lifecycle": draft.lifecycle,
                "issuer": draft.issuer,
                "edition": draft.edition,
                "issued": draft.issued,
                "valid_from": draft.valid_from,
            },
        )
        await connection.execute(
            "UPDATE document_profile SET term_mappings = %s, new_terms = %s WHERE document_id = %s",
            (
                Jsonb([dict(term) for term in draft.term_mappings]),
                Jsonb([dict(term) for term in draft.new_terms]),
                document_id,
            ),
        )
        if draft.evidence:
            await write_anchor(connection, document_id, conversion_id, _anchor(draft.evidence))
        keys: dict[str, UUID] = {}
        for specification in draft.specifications:
            made = await new_entity(connection, "specification")
            await connection.execute(
                _SPECIFICATION,
                (
                    made,
                    document_id,
                    specification.key,
                    specification.kind,
                    specification.title,
                    specification.field_text,
                    Jsonb(dict(specification.applicability)),
                ),
            )
            keys[specification.key] = made
            if specification.evidence:
                anchor = _anchor(specification.evidence)
                await write_anchor(connection, document_id, conversion_id, anchor, specification_id=made)
            for variant in specification.variants:
                variant_id = await new_entity(connection, "variant")
                await connection.execute(
                    _VARIANT,
                    (variant_id, made, variant.key, variant.label, CV + "VariantKinds", variant.kind),
                )
    return keys, notes


async def holds_extraction(connection: psycopg.AsyncConnection, document_id: UUID) -> bool:
    """Whether X1 wrote the document already: it holds a specification or a node. X1 writes onto
    a document of none - a tree is written after the siblings there (app/db/nodes.py), and a
    second profile would meet the first one's keys."""
    cursor = await connection.execute(
        "SELECT EXISTS (SELECT FROM node WHERE document_id = %(id)s)"
        " OR EXISTS (SELECT FROM specification WHERE document_id = %(id)s)",
        {"id": document_id},
    )
    found = await cursor.fetchone()
    return bool(found and found[0])


async def open_for_x1(connection: psycopg.AsyncConnection, document_id: UUID) -> bool:
    """Lock the document for X1's write, in the caller's transaction, and say whether X1 may write it:
    no run of X1 on it is done and nothing is written on it. A second job that asked meanwhile waits
    for the first one's commit here and then sees it (read committed)."""
    await connection.execute("SELECT 1 FROM document WHERE id = %s FOR NO KEY UPDATE", (document_id,))
    if "X1" in await done_stages(connection, document_id):
        return False
    return not await holds_extraction(connection, document_id)


async def suggest_work(
    connection: psycopg.AsyncConnection, title: str, regions: Sequence[str]
) -> UUID | None:
    """A work of the same title - in one case, its spaces one - in one of the regions, if any."""
    cursor = await connection.execute(_WORK, (list(regions), title))
    found = await cursor.fetchone()
    return None if found is None else found[0]


def _scheme(name: str, value: str | None) -> str | None:
    return None if value is None else CV + name


def _anchor(blocks: tuple[str, ...]) -> AnchorDraft:
    """An anchor at the blocks, over the pages they stand on (named by their ids, p<page>-b<n>)."""
    pages = [int(block[1 : block.index("-")]) for block in blocks]
    first, last = min(pages), max(pages)
    return AnchorDraft(block_ids=blocks, page_start=first, page_end=last if last > first else None)
