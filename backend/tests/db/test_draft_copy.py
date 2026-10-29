"""A frozen document's draft copy (plan M1 9.6, Paket 9b H7): a new revision under the same IRI, with all its
rows - nodes, statements and their addressees, anchors and their blocks, frame parts, specifications and
their variants, its profile - their IRIs, origins, review statuses and revisions, under ids of their own;
no findings and no runs, so X5 owes it a check. Of the latest revision alone, and one draft at most."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
import pytest

from app.db.anchors import new_entity
from app.db.draft_copy import CopyRefused, copy_document
from app.db.editing import add_node, edit_node, extracted
from app.db.freezing import freeze
from app.db.runs import x5_owed
from tests.db.test_editing import document, one
from tests.db.test_freeze import BASE, DOC, checked, ready
from tests.db.test_nodes import CV, connection, owner, url

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_editing

CONFIRMED = CV + "rev_confirmed"


@dataclass(frozen=True)
class Copy:
    id: UUID  # what checked() reads of a document


async def rows(connection: psycopg.AsyncConnection, query: str, document_id: Any) -> list[tuple[Any, ...]]:
    cursor = await connection.execute(query, {"document": document_id})
    return list(await cursor.fetchall())


async def content(connection: psycopg.AsyncConnection, document_id: Any) -> dict[str, list[tuple[Any, ...]]]:
    """What the document holds, named by IRIs and keys - not by the ids its rows have."""
    return {
        "nodes": await rows(connection, """
            SELECT n.iri, p.iri, n.position, n.code, n.original_title, n.origin_iri, n.review_status_iri,
                n.revision, n.statement_serial, n.run_id IS NULL,
                array(SELECT s.key FROM specification s WHERE s.id = ANY (n.applies_to)
                      UNION ALL SELECT v.key FROM variant v WHERE v.id = ANY (n.applies_to) ORDER BY 1)
            FROM node n LEFT JOIN node p ON p.id = n.parent_id
            WHERE n.document_id = %(document)s ORDER BY n.iri""", document_id),
        "statements": await rows(connection, """
            SELECT s.iri, n.iri, s.position, s.verbatim, s.origin_iri, s.review_status_iri, s.revision,
                s.by_hand, s.text_hash, s.run_id IS NULL,
                array(SELECT a.addressee_iri FROM statement_addressee a
                      WHERE a.statement_id = s.id ORDER BY 1)
            FROM statement s JOIN node n ON n.id = s.node_id
            WHERE s.document_id = %(document)s ORDER BY s.position, s.verbatim""", document_id),
        "anchors": await rows(connection, """
            SELECT coalesce(s.iri, n.iri, 'frame ' || f.part_kind, 'specification ' || sp.key, 'document'),
                a.page_start, a.match_kind_iri, a.quote,
                array(SELECT b.block_id FROM anchor_block b WHERE b.anchor_id = a.id ORDER BY 1)
            FROM anchor a LEFT JOIN statement s ON s.id = a.statement_id LEFT JOIN node n ON n.id = a.node_id
                LEFT JOIN frame_part f ON f.id = a.frame_part_id
                LEFT JOIN specification sp ON sp.id = a.specification_id
            WHERE a.document_id = %(document)s ORDER BY 1, 2""", document_id),
        "frame": await rows(connection, """
            SELECT part_kind, position, content, review_status_iri, run_id IS NULL FROM frame_part
            WHERE document_id = %(document)s""", document_id),
        "specifications": await rows(connection, """
            SELECT s.key, s.title, array(SELECT v.key || ' ' || v.label FROM variant v
                                         WHERE v.specification_id = s.id ORDER BY 1)
            FROM specification s WHERE s.document_id = %(document)s""", document_id),
        "profile": await rows(
            connection, "SELECT new_terms FROM document_profile WHERE document_id = %(document)s", document_id
        ),
    }  # fmt: skip


async def filled(connection: psycopg.AsyncConnection, document: Any) -> None:
    """``ready``'s document and all else a document holds: a confirmed statement, a frame part with an
    anchor, a specification with a variant the child node applies to, its profile; then frozen."""
    await ready(connection, document)
    await connection.execute(
        "UPDATE statement SET review_status_iri = %s, revision = 2 WHERE verbatim = 'Sie prüfen.'",
        (CONFIRMED,),
    )
    await connection.execute("UPDATE statement SET by_hand = true WHERE verbatim = 'Sie messen.'")
    frame, anchor = await new_entity(connection, "frame_part"), await new_entity(connection, "anchor")
    specification, variant = (
        await new_entity(connection, "specification"),
        await new_entity(connection, "variant"),
    )
    await connection.execute(
        "INSERT INTO frame_part (id, document_id, part_kind, content, origin_scheme, origin_iri,"
        " review_status_scheme, review_status_iri, position)"
        " VALUES (%s, %s, 'operators', '{\"o\": 1}', %s, %s, %s, %s, 1)",
        (frame, document.id, CV + "Origins", CV + "orig_model", CV + "ReviewStatuses", CV + "rev_proposed"),
    )
    await connection.execute(
        "INSERT INTO anchor (id, document_id, conversion_id, frame_part_id, page_start)"
        " VALUES (%s, %s, %s, %s, 2)",
        (anchor, document.id, document.conversion_id, frame),
    )
    await connection.execute(
        "INSERT INTO specification (id, document_id, key, spec_kind, title)"
        " VALUES (%s, %s, 'lp', 'curriculum', 'LP')",
        (specification, document.id),
    )
    await connection.execute(
        "INSERT INTO variant (id, specification_id, key, label, variant_kind_scheme, variant_kind_iri)"
        " VALUES (%s, %s, 'g8', 'G8', %s, %s)",
        (variant, specification, CV + "VariantKinds", CV + "var_track"),
    )
    await connection.execute(
        "UPDATE node SET applies_to = ARRAY[%s, %s]::uuid[] WHERE parent_id IS NOT NULL AND document_id = %s",
        (specification, variant, document.id),
    )
    await connection.execute(
        "UPDATE document_profile SET new_terms = '[\"Neu\"]' WHERE document_id = %s", (document.id,)
    )
    await freeze(connection, document.id, BASE, accept_violations=False)


async def test_a_copy_is_the_next_revision_with_all_its_rows_iris_and_review_statuses(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await filled(connection, document)
    before = await content(connection, document.id)

    copy = await copy_document(connection, document.id)

    assert await content(connection, copy) == before
    assert before["nodes"] and before["statements"] and before["anchors"] and before["frame"]
    assert await one(
        connection,
        "SELECT c.iri, c.revision, c.copy_of, c.frozen_at, c.draft_iri, c.edited_at IS NOT NULL,"
        " (c.owner_id, c.work_id, c.source_id, c.conversion_id, c.issuer, c.edition, c.title,"
        " c.rights_status) IS NOT DISTINCT FROM (d.owner_id, d.work_id, d.source_id, d.conversion_id,"
        " d.issuer, d.edition, d.title, d.rights_status)"
        " FROM document c, document d WHERE c.id = %s AND d.id = %s",
        copy,
        document.id,
    ) == (DOC, 2, document.id, None, copy.urn, True, True)
    # rows of their own, of entities of their own; none of the runs or findings
    assert await one(
        connection,
        "SELECT count(*) FROM node a JOIN node b ON a.id = b.id WHERE a.document_id <> b.document_id",
    ) == (0,)
    assert await one(
        connection,
        "SELECT (SELECT count(*) FROM extraction_run WHERE document_id = %s),"
        " (SELECT count(*) FROM validation_finding WHERE document_id = %s),"
        " (SELECT count(*) FROM entity e JOIN node n ON n.id = e.id WHERE n.document_id = %s)",
        copy, copy, copy,
    ) == (0, 0, len(before["nodes"]))  # fmt: skip


async def test_a_copy_is_extracted_x5_owes_it_a_check_and_its_frozen_source_stays(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await filled(connection, document)
    before = await content(connection, document.id)

    copy = await copy_document(connection, document.id)

    assert (await extracted(connection, copy), await x5_owed(connection, copy)) == (True, True)
    assert await content(connection, document.id) == before
    assert await one(connection, "SELECT frozen_at IS NOT NULL FROM document WHERE id = %s", document.id) == (
        True,
    )


async def test_a_copy_is_of_the_latest_frozen_revision_and_one_draft_at_most(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await ready(connection, document)
    with pytest.raises(CopyRefused) as not_frozen:
        await copy_document(connection, document.id)
    await freeze(connection, document.id, BASE, accept_violations=False)
    copy = await copy_document(connection, document.id)

    with pytest.raises(CopyRefused) as open_draft:
        await copy_document(connection, document.id)
    await connection.execute("UPDATE document SET frozen_at = now() WHERE id = %s", (copy,))
    with pytest.raises(CopyRefused) as earlier:
        await copy_document(connection, document.id)

    assert not_frozen.value.code == "not_frozen"
    assert (open_draft.value.code, open_draft.value.details) == ("draft_open", {"document_id": str(copy)})
    assert earlier.value.code == "not_latest"
    assert await one(connection, "SELECT count(*) FROM document WHERE iri = %s", DOC) == (2,)


async def test_a_copy_is_edited_checked_and_frozen_as_the_next_revision_the_one_before_readable(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await filled(connection, document)
    before = await content(connection, document.id)
    copy = await copy_document(connection, document.id)
    cursor = await connection.execute(
        "SELECT id FROM node WHERE document_id = %s AND parent_id IS NULL", (copy,)
    )
    [(top,)] = await cursor.fetchall()

    # a copy is all there: its tree takes changes at once (no X4 of its own)
    await edit_node(connection, owner(document), top, 1, {"code": "LF 7"})
    added = await add_node(
        connection, owner(document), copy, top, {"original_title": "Neu", "function": CV + "fn_unit"}
    )
    await checked(connection, Copy(copy))
    frozen = await freeze(connection, copy, BASE, accept_violations=False)

    assert (frozen.iri, frozen.revision, frozen.nodes, frozen.statements) == (DOC, 2, 1, 0)
    assert await one(connection, "SELECT iri FROM node WHERE id = %s", top) == (DOC + "/lf-1",)  # it stays
    assert await one(connection, "SELECT iri FROM node WHERE id = %s", added) == (DOC + "/lf-1/pos-2",)
    assert await content(connection, document.id) == before
    assert await one(
        connection, "SELECT count(*) FROM document WHERE iri = %s AND frozen_at IS NOT NULL", DOC
    ) == (2,)
