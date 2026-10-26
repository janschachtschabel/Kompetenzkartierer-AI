"""The editors' review of a document's nodes and statements (plan M1 9.5; Paket 9 G8, app/db/review.py):
one status for many rows at once, all or nothing - each on the revision it was read at -, the rows' origin
kept; beside the tree's other writes, not beside an open job or once the document is frozen. A statement
rejected, or taken back from rejected, changes what the curriculum says: the document is edited."""

import uuid
from typing import Any

import psycopg
import pytest

from app.db.documents import create_document
from app.db.editing import DocumentFrozen, JobOpen
from app.db.nodes import write_subtree
from app.db.review import ReviewItem, Stale, StaleItems, set_review
from tests.db.test_editing import an_open_job, edited_at, one
from tests.db.test_nodes import CV, connection, document, node, owner, statement, url

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_nodes

MODEL = CV + "orig_model"
PROPOSED, CONFIRMED, REJECTED = CV + "rev_proposed", CV + "rev_confirmed", CV + "rev_rejected"


async def a_tree(connection: psycopg.AsyncConnection, document: Any) -> tuple[Any, list[Any]]:
    """A node of the model's with two statements: the node's id and the statements'."""
    top = await write_subtree(
        connection,
        document.id,
        node(origin=MODEL, statements=(statement("Sie messen.", origin=MODEL), statement("Sie prüfen."))),
    )
    cursor = await connection.execute("SELECT id FROM statement WHERE node_id = %s ORDER BY position", (top,))
    return top, [found for (found,) in await cursor.fetchall()]


async def states(connection: psycopg.AsyncConnection) -> list[tuple[Any, ...]]:
    cursor = await connection.execute(
        "SELECT kind, origin_iri, review_status_iri, revision FROM ("
        " SELECT 'node' AS kind, position, origin_iri, review_status_iri, revision FROM node"
        " UNION ALL SELECT 'statement', position, origin_iri, review_status_iri, revision FROM statement"
        ") AS row ORDER BY kind, position"
    )
    return [tuple(found) for found in await cursor.fetchall()]


async def test_the_editors_confirm_rows_at_once_and_their_origin_stays(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top, (measured, checked) = await a_tree(connection, document)

    revisions = await set_review(
        connection,
        document.id,
        CONFIRMED,
        [
            ReviewItem("node", top, 1),
            ReviewItem("statement", measured, 1),
            ReviewItem("statement", checked, 1),
        ],
    )

    assert revisions == {top: 2, measured: 2, checked: 2}
    assert await states(connection) == [
        ("node", MODEL, CONFIRMED, 2),
        ("statement", MODEL, CONFIRMED, 2),
        ("statement", CV + "orig_source", CONFIRMED, 2),
    ]
    assert await edited_at(connection, document) is None  # a review changes not what the document says


async def test_a_row_at_its_status_already_stays_as_it_is(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top, (measured, _) = await a_tree(connection, document)

    assert await set_review(connection, document.id, PROPOSED, [ReviewItem("node", top, 1)]) == {top: 1}
    assert await set_review(
        connection,
        document.id,
        CONFIRMED,
        [ReviewItem("statement", measured, 1), ReviewItem("statement", measured, 1)],
    ) == {measured: 2}  # named twice, set once
    assert (await states(connection))[0] == ("node", MODEL, PROPOSED, 1)


async def test_one_stale_row_leaves_every_row_as_it_was(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top, (measured, checked) = await a_tree(connection, document)
    before = await states(connection)
    gone = uuid.uuid4()

    with pytest.raises(StaleItems) as raised:
        await set_review(
            connection,
            document.id,
            CONFIRMED,
            [
                ReviewItem("node", top, 1),
                ReviewItem("statement", measured, 2),  # read before a change
                ReviewItem("statement", gone, 1),  # taken away meanwhile
                ReviewItem("node", checked, 1),  # a statement, not a node
            ],
        )

    assert raised.value.stale == [
        Stale("statement", measured, 1), Stale("statement", gone, None), Stale("node", checked, None),
    ]  # fmt: skip
    assert await states(connection) == before


async def test_a_row_of_another_document_is_none_of_this_one(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top, _ = await a_tree(connection, document)
    other = await create_document(
        connection, owner(document), third_party_content=False, source_id=document.source_id,
        conversion_id=document.conversion_id, sector="school",
    )  # fmt: skip

    with pytest.raises(StaleItems) as raised:
        await set_review(connection, other.id, CONFIRMED, [ReviewItem("node", top, 1)])

    assert raised.value.stale == [Stale("node", top, None)]


async def test_a_statement_rejected_or_taken_back_edits_the_document(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top, (measured, _) = await a_tree(connection, document)

    await set_review(connection, document.id, REJECTED, [ReviewItem("node", top, 1)])
    assert await edited_at(connection, document) is None  # a node rejected stays in the curriculum
    await set_review(connection, document.id, REJECTED, [ReviewItem("statement", measured, 1)])
    first = await edited_at(connection, document)
    assert first is not None
    await connection.execute("UPDATE document SET edited_at = NULL")
    await set_review(connection, document.id, CONFIRMED, [ReviewItem("statement", measured, 2)])

    assert await edited_at(connection, document) is not None


async def test_no_review_is_set_beside_an_open_job_or_of_a_frozen_document(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top, _ = await a_tree(connection, document)
    job = await an_open_job(connection, document)

    with pytest.raises(JobOpen):
        await set_review(connection, document.id, CONFIRMED, [ReviewItem("node", top, 1)])
    await connection.execute("UPDATE job SET status = 'done', finished_at = now() WHERE id = %s", (job,))
    await connection.execute(
        "UPDATE document SET iri = 'https://example.org/curriculum/1', frozen_at = now() WHERE id = %s",
        (document.id,),
    )
    with pytest.raises(DocumentFrozen):
        await set_review(connection, document.id, CONFIRMED, [ReviewItem("node", top, 1)])
    assert await one(connection, "SELECT max(revision) FROM node") == (1,)
