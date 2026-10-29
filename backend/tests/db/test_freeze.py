"""A document frozen by the editors (plan M1 9.6, Paket 9b H5, H6): under the tree's lock, once it is
extracted, has its work, issuer and edition, a base to name it under, and X5's check of all it says -
its violations accepted, where it has any; then its work, the document, its nodes and statements get
their IRIs and it changes no more. Each condition unmet refuses with its own reason, and nothing is
changed."""

from typing import Any

import psycopg
import pytest
from psycopg import errors

from app.db.document_meta import NewWork, set_work
from app.db.documents import create_document
from app.db.editing import DocumentFrozen, JobOpen, NotExtracted, edit_node
from app.db.freezing import FreezeRefused, Frozen, freeze
from app.db.nodes import write_subtree
from app.db.runs import RunStart, finish_run, stage_iri, start_run
from tests.db.test_editing import an_open_job, document, extracted
from tests.db.test_nodes import CV, anchor, connection, node, owner, statement, url

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_editing

BASE = "https://example.org/kk/"
DOC = BASE + "doc/ministerium-fuer-schule/lp-physik/2024"
REJECTED = CV + "rev_rejected"


async def checked(connection: psycopg.AsyncConnection, document: Any) -> None:
    """X5 done on the document, after all it says: no check owed."""
    run = await start_run(connection, RunStart(document.id, None, None, "X5", None, None, None, None))
    await finish_run(connection, run, "done")


async def ready(connection: psycopg.AsyncConnection, document: Any) -> Any:
    """The document with its work, issuer and edition, a node with three statements - one rejected -
    and a child of no code, every anchor found, and X5 done after: one to freeze."""
    await set_work(connection, owner(document), document.id, NewWork("Lehrplan Physik", "DE-NW", "lp-physik"))
    await connection.execute(
        "UPDATE document SET issuer = 'Ministerium für Schule', edition = '2024' WHERE id = %s",
        (document.id,),
    )
    top = await write_subtree(connection, document.id, node(
        code="LF 1", original_title="Optik",
        statements=(statement("Sie messen."), statement("Verworfen.", review_status=REJECTED),
                    statement("Sie prüfen.")),
        children=(node("fn_unit", original_title="Licht"),),
    ))  # fmt: skip
    await connection.execute(
        "UPDATE anchor SET match_kind_scheme = %s, match_kind_iri = %s WHERE document_id = %s",
        (CV + "MatchKinds", CV + "match_exact", document.id),
    )
    await checked(connection, document)
    return top


async def iris(connection: psycopg.AsyncConnection, document: Any) -> dict[str, Any]:
    cursor = await connection.execute(
        "SELECT d.iri, d.frozen_at IS NOT NULL, w.iri FROM document d JOIN work w ON w.id = d.work_id"
        " WHERE d.id = %s",
        (document.id,),
    )
    found = await cursor.fetchone()
    assert found is not None
    nodes = await connection.execute(
        "SELECT iri, statement_serial FROM node WHERE document_id = %s ORDER BY parent_id NULLS FIRST",
        (document.id,),
    )
    said = await connection.execute(
        "SELECT verbatim, iri FROM statement WHERE document_id = %s ORDER BY position", (document.id,)
    )
    return {
        "document": found[0], "frozen": found[1], "work": found[2],
        "nodes": await nodes.fetchall(), "statements": await said.fetchall(),
    }  # fmt: skip


async def test_a_ready_document_is_frozen_with_the_iris_of_its_work_nodes_and_statements(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await ready(connection, document)

    frozen = await freeze(connection, document.id, BASE, accept_violations=False)

    assert frozen == Frozen(iri=DOC, revision=1, nodes=2, statements=2, violations=0)
    assert await iris(connection, document) == {
        "document": DOC,
        "frozen": True,
        "work": BASE + "work/de-nw/lp-physik",
        "nodes": [(DOC + "/lf-1", 2), (DOC + "/lf-1/pos-1", 0)],
        # the rejected statement is none of the curriculum's: no IRI, no number taken
        "statements": [
            ("Sie messen.", DOC + "/lf-1/s-1"),
            ("Verworfen.", None),
            ("Sie prüfen.", DOC + "/lf-1/s-2"),
        ],
    }


async def test_a_frozen_document_takes_no_change_after(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top = await ready(connection, document)
    await freeze(connection, document.id, BASE, accept_violations=False)

    with pytest.raises(DocumentFrozen):
        await edit_node(connection, owner(document), top, 1, {"code": "2"})
    with pytest.raises(DocumentFrozen):
        await freeze(connection, document.id, BASE, accept_violations=False)
    with pytest.raises(errors.ObjectNotInPrerequisiteState):
        await connection.execute("UPDATE node SET code = '2' WHERE id = %s", (top,))


async def test_violations_are_frozen_with_where_the_editors_accept_them(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top = await ready(connection, document)
    await connection.execute(
        "INSERT INTO validation_finding (id, document_id, rule, severity, focus_id, message)"
        " VALUES (gen_random_uuid(), %s, 'shacl.NodeShape', 'violation', %s, 'Verstoß')",
        (document.id, top),
    )

    with pytest.raises(FreezeRefused) as refused:
        await freeze(connection, document.id, BASE, accept_violations=False)
    assert (refused.value.code, refused.value.details) == ("has_violations", {"violations": 1})
    assert (await iris(connection, document))["frozen"] is False

    frozen = await freeze(connection, document.id, BASE, accept_violations=True)
    assert frozen.violations == 1


async def test_a_document_short_of_its_work_issuer_or_edition_is_refused_with_what_it_lacks(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await ready(connection, document)
    await connection.execute("UPDATE work SET short_title = NULL, region = NULL")
    await connection.execute("UPDATE document SET edition = NULL WHERE id = %s", (document.id,))

    with pytest.raises(FreezeRefused) as short:
        await freeze(connection, document.id, BASE, accept_violations=False)
    await connection.execute(
        "UPDATE document SET work_id = NULL, issuer = NULL WHERE id = %s", (document.id,)
    )
    with pytest.raises(FreezeRefused) as none:
        await freeze(connection, document.id, BASE, accept_violations=False)

    assert (short.value.code, short.value.details) == (
        "incomplete",
        {"missing": ["region", "short_title", "edition"]},
    )
    assert none.value.details == {"missing": ["work", "issuer", "edition"]}


async def test_an_issuer_or_edition_with_nothing_to_name_it_by_is_what_the_document_lacks(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    # the document's IRI is named by them (app/domain/iris.py): a bullet or a Greek letter names nothing
    await ready(connection, document)
    await connection.execute("UPDATE document SET issuer = '•', edition = 'Ω' WHERE id = %s", (document.id,))

    with pytest.raises(FreezeRefused) as unnamed:
        await freeze(connection, document.id, BASE, accept_violations=False)

    assert (unnamed.value.code, unnamed.value.details) == ("incomplete", {"missing": ["issuer", "edition"]})


async def test_no_document_is_frozen_without_a_base_to_name_it_under(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await ready(connection, document)

    with pytest.raises(FreezeRefused) as refused:
        await freeze(connection, document.id, None, accept_violations=False)

    assert refused.value.code == "no_iri_base"


async def test_a_document_x5_owes_a_check_or_with_an_anchor_unchecked_is_refused(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await ready(connection, document)
    await connection.execute(
        "UPDATE anchor SET match_kind_scheme = NULL, match_kind_iri = NULL WHERE statement_id ="
        " (SELECT id FROM statement WHERE verbatim = 'Sie messen.')"
    )
    with pytest.raises(FreezeRefused) as unchecked:
        await freeze(connection, document.id, BASE, accept_violations=False)
    await connection.execute(
        "UPDATE anchor SET match_kind_scheme = %s, match_kind_iri = %s WHERE match_kind_iri IS NULL",
        (CV + "MatchKinds", CV + "match_exact"),
    )
    await connection.execute("UPDATE document SET edited_at = now() WHERE id = %s", (document.id,))
    with pytest.raises(FreezeRefused) as owed:
        await freeze(connection, document.id, BASE, accept_violations=False)

    assert (unchecked.value.code, unchecked.value.details) == ("check_owed", {"unchecked": 1})
    assert (owed.value.code, owed.value.details) == ("check_owed", {"unchecked": 0})
    assert (await iris(connection, document))["frozen"] is False


async def test_a_document_x5_never_checked_is_refused_though_nobody_edited_it(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    # no X6 and no edit: x5_owed finds nothing owed where no check was ever done
    await ready(connection, document)
    await connection.execute(
        "DELETE FROM extraction_run WHERE document_id = %s AND stage_iri = %s", (document.id, stage_iri("X5"))
    )

    with pytest.raises(FreezeRefused) as never:
        await freeze(connection, document.id, BASE, accept_violations=False)

    assert (never.value.code, never.value.details) == ("check_owed", {"unchecked": 0})


async def test_an_unchecked_anchor_of_a_rejected_statement_holds_nothing_up(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    # X5 checks no rejected statement (app/db/anchors.py): its anchors stay as they were
    await ready(connection, document)
    await connection.execute(
        "UPDATE anchor SET match_kind_scheme = NULL, match_kind_iri = NULL WHERE statement_id ="
        " (SELECT id FROM statement WHERE verbatim = 'Verworfen.')"
    )

    assert (await freeze(connection, document.id, BASE, accept_violations=False)).iri == DOC


async def test_the_title_of_a_node_x4_made_for_a_unit_of_none_holds_nothing_up(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    # its title is the document's, not a wording of its blocks: X5 never checks its anchor
    await ready(connection, document)
    await write_subtree(connection, document.id, node(
        "fn_unit", original_title="Dokument", origin=CV + "orig_rule", rule_id="x4.unit_without_node",
        anchors=(anchor("p1-b1"),),
    ))  # fmt: skip

    assert (await freeze(connection, document.id, BASE, accept_violations=False)).nodes == 3


async def test_a_document_beside_its_job_or_before_x4_is_not_frozen(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await ready(connection, document)
    early = await create_document(
        connection, owner(document), third_party_content=False, source_id=document.source_id,
        conversion_id=document.conversion_id, sector="school",
    )  # fmt: skip
    await an_open_job(connection, document)

    with pytest.raises(JobOpen):
        await freeze(connection, document.id, BASE, accept_violations=False)
    with pytest.raises(NotExtracted):
        await freeze(connection, early.id, BASE, accept_violations=False)
    await extracted(connection, early)  # then on to what it lacks
    with pytest.raises(FreezeRefused):
        await freeze(connection, early.id, BASE, accept_violations=False)


async def test_an_iri_another_document_or_work_holds_is_refused(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await ready(connection, document)
    other = await create_document(
        connection, owner(document), third_party_content=False, source_id=document.source_id,
        conversion_id=document.conversion_id, sector="school",
    )  # fmt: skip
    await connection.execute("UPDATE document SET iri = %s, frozen_at = now() WHERE id = %s", (DOC, other.id))
    with pytest.raises(FreezeRefused) as document_taken:
        await freeze(connection, document.id, BASE, accept_violations=False)
    # the work's IRI is looked at first
    third = await create_document(
        connection, owner(document), third_party_content=False, source_id=document.source_id,
        conversion_id=document.conversion_id, sector="school",
    )  # fmt: skip
    work = await set_work(connection, owner(document), third.id, NewWork("Andere", "DE-BY", "andere"))
    await connection.execute("UPDATE work SET iri = %s WHERE id = %s", (BASE + "work/de-nw/lp-physik", work))
    with pytest.raises(FreezeRefused) as work_taken:
        await freeze(connection, document.id, BASE, accept_violations=False)

    assert (document_taken.value.code, document_taken.value.details) == ("iri_taken", {"iri": DOC})
    assert work_taken.value.details == {"iri": BASE + "work/de-nw/lp-physik"}
    assert (await iris(connection, document))["frozen"] is False
