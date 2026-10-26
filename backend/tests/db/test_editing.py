"""An editor's changes to a document's nodes (plan M1 9.3; Paket 9 G2-G6, app/db/editing.py): a node's
fields set by the form's keys, a node added after its siblings, a node dropped with its subtree and the
findings on it. Each change names the revision it was made on and makes the node an editor's proposal;
none is made beside an open job of the document or once it is frozen, each waits for the tree's lock."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import psycopg
import pytest

from app.db.documents import create_document
from app.db.editing import DocumentFrozen, Dropped, JobOpen, StaleRevision, add_node, drop_node, edit_node
from app.db.nodes import lock_tree, write_subtree
from app.db.source_queries import Reader
from app.domain.l1 import AnchorDraft
from app.jobs.queue import enqueue
from app.pipeline.extraction import KIND, unique_key
from app.vocab.form_values import FieldError
from tests.db.test_nodes import (
    CV,
    SCHOOL,
    anchor,
    connection,
    document,
    node,
    owner,
    statement,
    url,
    waiting_for_a_lock,
)

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_nodes

HUMAN, RULE = CV + "orig_human", CV + "orig_rule"
PROPOSED, CONFIRMED = CV + "rev_proposed", CV + "rev_confirmed"
EXACT = CV + "match_exact"


async def one(connection: psycopg.AsyncConnection, query: str, *params: Any) -> tuple[Any, ...]:
    cursor = await connection.execute(query, params)
    found = await cursor.fetchone()
    assert found is not None
    return tuple(found)


async def node_row(connection: psycopg.AsyncConnection, node_id: Any) -> tuple[Any, ...]:
    return await one(
        connection,
        "SELECT original_title, function_iri, node_type_iri, code, code_assigned, obligation_iri, origin_iri,"
        " rule_id, review_status_iri, revision FROM node WHERE id = %s",
        node_id,
    )


async def edited_at(connection: psycopg.AsyncConnection, document: Any) -> Any:
    return (await one(connection, "SELECT edited_at FROM document WHERE id = %s", document.id))[0]


async def a_rule_s_node(connection: psycopg.AsyncConnection, document: Any, **changes: Any) -> uuid.UUID:
    """A unit X1's rules made and an editor confirmed: code 1 from its position, titled Optik."""
    values: dict[str, Any] = {
        "code": "1", "code_assigned": True, "original_title": "Optik", "origin": RULE,
        "rule_id": "x1.heading", "review_status": CONFIRMED,
    } | changes  # fmt: skip
    return await write_subtree(connection, document.id, node("fn_unit", **values))


async def an_open_job(connection: psycopg.AsyncConnection, document: Any) -> uuid.UUID:
    return await enqueue(
        connection,
        KIND,
        str(document.owner_id),
        {"document_id": str(document.id)},
        unique_key=unique_key(document.id),
    )


async def test_an_edit_sets_the_fields_and_makes_the_node_an_editor_s_proposal(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)
    assert await edited_at(connection, document) is None

    revision = await edit_node(
        connection, owner(document), made, 1, {"code": "2", "obligation": CV + "obl_binding"}
    )

    assert revision == 2
    assert await node_row(connection, made) == (
        "Optik", CV + "fn_unit", None, "2", False, CV + "obl_binding", HUMAN, None, PROPOSED, 2,
    )  # fmt: skip
    assert await edited_at(connection, document) is not None


async def test_an_edit_of_a_stale_revision_is_refused_and_changes_nothing(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)
    before = await node_row(connection, made)

    with pytest.raises(StaleRevision) as raised:
        await edit_node(connection, owner(document), made, 2, {"code": "2"})

    assert raised.value.current == 1
    assert await node_row(connection, made) == before
    assert await edited_at(connection, document) is None


async def test_an_edit_that_changes_nothing_leaves_the_node_as_it_was(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)
    before = await node_row(connection, made)

    assert (
        await edit_node(connection, owner(document), made, 1, {"code": "1", "original_title": "Optik"}) == 1
    )

    assert await node_row(connection, made) == before
    assert await edited_at(connection, document) is None


async def test_a_new_title_leaves_the_node_s_anchors_unchecked(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    checked = AnchorDraft(
        block_ids=("p1-b1",), page_start=1, quote="Optik", match_kind=EXACT, match_score=1.0
    )
    missed = AnchorDraft(block_ids=(), page_start=2, match_kind=CV + "match_notFound")
    made = await a_rule_s_node(connection, document, anchors=(checked, missed))
    query = (
        "SELECT a.match_kind_iri, a.match_score, a.quote, count(ab.block_id) FROM anchor a"
        " LEFT JOIN anchor_block ab ON ab.anchor_id = a.id WHERE a.node_id = %s GROUP BY a.id ORDER BY a.id"
    )

    await edit_node(connection, owner(document), made, 1, {"code": "2"})
    cursor = await connection.execute(query, (made,))
    assert await cursor.fetchall() == [(EXACT, 1.0, "Optik", 1), (CV + "match_notFound", None, None, 0)]

    await edit_node(connection, owner(document), made, 2, {"original_title": "Licht"})
    cursor = await connection.execute(query, (made,))
    # X5 checks the anchor with blocks anew; the one an editor found no passage for stays so
    assert await cursor.fetchall() == [(None, None, None, 1), (CV + "match_notFound", None, None, 0)]


async def test_a_field_the_node_may_not_take_is_refused_and_changes_nothing(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)
    before = await node_row(connection, made)

    for given, problem in (
        ({"node_type": SCHOOL + "Inhaltsbereich"}, ("node_type", "not_under")),  # an area's, not a unit's
        ({"original_title": None}, ("original_title", "required")),
        ({"function": CV + "fn_nowhere"}, ("function", "not_offered")),
        ({"position": 2}, ("position", "unknown")),
    ):
        with pytest.raises(FieldError) as raised:
            await edit_node(connection, owner(document), made, 1, given)
        assert (raised.value.key, raised.value.problem) == problem
    assert await node_row(connection, made) == before


async def test_a_node_type_and_its_function_are_changed_together(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)

    await edit_node(
        connection,
        owner(document),
        made,
        1,
        {"function": CV + "fn_area", "node_type": SCHOOL + "Inhaltsbereich"},
    )

    assert (await node_row(connection, made))[1:3] == (CV + "fn_area", SCHOOL + "Inhaltsbereich")


async def test_a_new_node_goes_after_its_siblings_as_an_editor_s_proposal(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top = await write_subtree(connection, document.id, node(children=(node("fn_unit", code="1"),)))
    fields = {"original_title": "Licht", "function": CV + "fn_unit", "code": "2"}

    child = await add_node(connection, owner(document), document.id, top, fields)
    second = await add_node(
        connection, owner(document), document.id, None, fields | {"function": CV + "fn_area"}
    )

    assert child is not None and second is not None
    assert await one(connection, "SELECT parent_id, position FROM node WHERE id = %s", child) == (top, 2)
    assert await one(connection, "SELECT parent_id, position FROM node WHERE id = %s", second) == (None, 2)
    assert await node_row(connection, child) == (
        "Licht", CV + "fn_unit", None, "2", False, None, HUMAN, None, PROPOSED, 1,
    )  # fmt: skip
    assert await edited_at(connection, document) is not None


async def test_a_new_node_has_the_fields_its_form_asks_for(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    with pytest.raises(FieldError) as raised:
        await add_node(connection, owner(document), document.id, None, {"function": CV + "fn_area"})

    assert (raised.value.key, raised.value.problem) == ("original_title", "required")
    with pytest.raises(FieldError) as raised:
        await add_node(connection, owner(document), document.id, None, {"original_title": "Licht"})
    assert (raised.value.key, raised.value.problem) == ("function", "required")
    assert await one(connection, "SELECT count(*) FROM node") == (0,)


async def test_a_dropped_node_takes_its_subtree_and_the_findings_on_it(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    root = await write_subtree(
        connection,
        document.id,
        node(
            statements=(statement("Sie lesen."),),
            children=(
                node("fn_unit", anchors=(anchor("p1-b1"),), statements=(statement("Sie messen."),),
                     children=(node("fn_unit", statements=(statement("Sie prüfen."),
                                                           statement("Sie rechnen."))),)),
            ),
        ),
    )  # fmt: skip
    dropped = await one(connection, "SELECT id FROM node WHERE parent_id = %s", root)
    kept_finding = await a_finding(connection, document, root)
    for focus in await ids(connection, dropped):
        await a_finding(connection, document, focus)
    entities = await one(connection, "SELECT count(*) FROM entity")

    with pytest.raises(StaleRevision):
        await drop_node(connection, owner(document), dropped[0], 2)
    gone = await drop_node(connection, owner(document), dropped[0], 1)

    assert gone == Dropped(nodes=2, statements=3)
    assert await one(connection, "SELECT count(*) FROM node") == (1,)
    assert await one(connection, "SELECT count(*), max(verbatim) FROM statement") == (1, "Sie lesen.")
    assert await one(connection, "SELECT array_agg(id) FROM validation_finding") == ([kept_finding],)
    assert await one(connection, "SELECT count(*) FROM entity") == entities  # entities stay, as everywhere
    assert await edited_at(connection, document) is not None


async def a_finding(connection: psycopg.AsyncConnection, document: Any, focus: Any) -> uuid.UUID:
    made = uuid.uuid4()
    await connection.execute(
        "INSERT INTO validation_finding (id, document_id, rule, severity, focus_id, message)"
        " VALUES (%s, %s, 'x5.test', 'warning', %s, 'found')",
        (made, document.id, focus),
    )
    return made


async def ids(connection: psycopg.AsyncConnection, top: tuple[Any, ...]) -> list[Any]:
    """The subtree's nodes, statements and anchors of both."""
    cursor = await connection.execute(
        "WITH RECURSIVE under (id) AS (SELECT %s::uuid UNION ALL SELECT n.id FROM node n JOIN under u"
        " ON n.parent_id = u.id)"
        " SELECT id FROM under UNION ALL SELECT s.id FROM statement s JOIN under u ON s.node_id = u.id"
        " UNION ALL SELECT a.id FROM anchor a LEFT JOIN statement s ON s.id = a.statement_id"
        " JOIN under u ON u.id = coalesce(a.node_id, s.node_id)",
        (top[0],),
    )
    return [found for (found,) in await cursor.fetchall()]


def changes(
    connection: psycopg.AsyncConnection, document: Any, made: uuid.UUID
) -> list[Callable[[], Awaitable[object]]]:
    """An edit, an addition and a drop, each of the node ``made`` or beside it, each for a call."""
    fields = {"original_title": "Licht", "function": CV + "fn_area"}
    return [
        lambda: edit_node(connection, owner(document), made, 1, {"code": "2"}),
        lambda: add_node(connection, owner(document), document.id, None, fields),
        lambda: drop_node(connection, owner(document), made, 1),
    ]


async def test_no_change_is_made_beside_an_open_job_of_the_document(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)
    job = await an_open_job(connection, document)

    for change in changes(connection, document, made):
        with pytest.raises(JobOpen) as raised:
            await change()
        assert raised.value.job_id == job
    assert await one(connection, "SELECT count(*), max(revision) FROM node") == (1, 1)


async def test_no_change_is_made_to_a_frozen_document(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)
    await connection.execute(
        "UPDATE document SET iri = 'https://example.org/curriculum/1', frozen_at = now() WHERE id = %s",
        (document.id,),
    )

    for change in changes(connection, document, made):
        with pytest.raises(DocumentFrozen):
            await change()
    assert await one(connection, "SELECT count(*), max(revision) FROM node") == (1, 1)


async def test_an_edit_waits_for_the_tree_and_then_meets_the_job_started_meanwhile(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    # the lock first, the open job after: a start between the two cannot slip past the check
    made = await a_rule_s_node(connection, document)
    async with (
        await psycopg.AsyncConnection.connect(url, autocommit=True) as other,
        await psycopg.AsyncConnection.connect(url, autocommit=True) as watcher,
    ):
        waiting: asyncio.Task[int | None] | None = None
        try:
            async with other.transaction():
                await lock_tree(other, document.id)
                waiting = asyncio.create_task(edit_node(connection, owner(document), made, 1, {"code": "2"}))
                await waiting_for_a_lock(watcher, connection.info.backend_pid)
                job = await an_open_job(other, document)
        finally:
            with pytest.raises(JobOpen) as raised:
                if waiting is not None:
                    await waiting

    assert raised.value.job_id == job
    assert (await node_row(connection, made))[3] == "1"


async def test_a_new_node_goes_under_a_parent_of_its_own_document_alone(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    other = await create_document(
        connection, owner(document), third_party_content=False, source_id=document.source_id,
        conversion_id=document.conversion_id, sector="school",
    )  # fmt: skip
    elsewhere = await write_subtree(connection, other.id, node())
    fields = {"original_title": "Licht", "function": CV + "fn_unit"}

    for who in (owner(document), Reader(uuid.uuid4(), sees_all=True)):
        assert await add_node(connection, who, document.id, elsewhere, fields) is None
    assert await one(connection, "SELECT count(*) FROM node") == (1,)


async def test_a_node_is_none_to_who_sees_not_its_document(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await a_rule_s_node(connection, document)
    stranger = Reader(uuid.uuid4(), sees_all=False)
    editor = Reader(uuid.uuid4(), sees_all=True)
    fields = {"original_title": "Licht", "function": CV + "fn_area"}

    assert await edit_node(connection, stranger, made, 1, {"code": "2"}) is None
    assert await drop_node(connection, stranger, made, 1) is None
    assert await add_node(connection, stranger, document.id, None, fields) is None
    assert await edit_node(connection, owner(document), uuid.uuid4(), 1, {"code": "2"}) is None
    assert await add_node(connection, owner(document), document.id, uuid.uuid4(), fields) is None
    assert (await node_row(connection, made))[-1] == 1
    assert await edit_node(connection, editor, made, 1, {"code": "2"}) == 2  # the editors see every one
