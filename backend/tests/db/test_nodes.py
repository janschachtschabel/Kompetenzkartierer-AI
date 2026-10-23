"""Writing a document's structure as one subtree at a time and reading it back as a tree (plan M1
4.6): a subtree is written whole or not at all, and read only by those who see its document."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.core.ids import new_id
from app.db.documents import DocumentError, ProfileValueError, create_document
from app.db.migrate import migrate
from app.db.nodes import lock_tree, read_tree, write_subtree
from app.db.source_queries import Reader
from app.domain.l1 import AnchorDraft, NodeDraft, StatementDraft
from app.domain.wording import text_hash
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.l1 import add_conversion, add_run

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
CV = "https://w3id.org/wlo/curriculum/vocab#"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
VOCATIONAL = "https://w3id.org/wlo/curriculum/profile/vocational#"
SOURCE, PROPOSED = CV + "orig_source", CV + "rev_proposed"


@pytest.fixture
def url(database_url: str) -> str:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    return database_url


@pytest.fixture
async def connection(url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as opened:
        yield opened


@pytest.fixture
async def document(url: str, connection: psycopg.AsyncConnection) -> Any:
    with psycopg.connect(url, autocommit=True) as sync:
        made = add_conversion(sync)
    return await create_document(
        connection,
        Reader(made["owner"], sees_all=False),
        third_party_content=False,
        source_id=made["source"],
        conversion_id=made["conversion"],
        sector="school",
    )


def anchor(*blocks: str, page: int = 1) -> AnchorDraft:
    return AnchorDraft(block_ids=blocks, page_start=page)


def statement(verbatim: str, **changes: Any) -> StatementDraft:
    values: dict[str, Any] = {
        "verbatim": verbatim,
        "kind": CV + "kind_learningOutcome",
        "addressees": (CV + "addr_learner",),
        "anchors": (anchor("p1-b1"),),
        "origin": SOURCE,
        "review_status": PROPOSED,
    } | changes
    return StatementDraft(**values)


def node(function: str = "fn_area", **changes: Any) -> NodeDraft:
    values: dict[str, Any] = {
        "function": CV + function,
        "origin": SOURCE,
        "review_status": PROPOSED,
    } | changes
    return NodeDraft(**values)


AREA = node(
    node_type=SCHOOL + "Inhaltsbereich",
    original_title="Zahlen und Operationen",
    anchors=(anchor("p1-b1"),),
    children=(
        node(
            "fn_unit",
            code="1",
            statements=(
                statement(
                    "Die Lernenden rechnen im Kopf.",
                    subkind=SCHOOL + "Kompetenzerwartung",
                    addressees=(CV + "addr_learner", CV + "addr_educator"),
                    anchors=(anchor("p1-b1", "p2-b1", page=1),),
                ),
                statement("Sie prüfen ihre Ergebnisse."),
            ),
        ),
        node("fn_unit", code="2"),
    ),
)


def owner(document: Any) -> Reader:
    return Reader(document.owner_id, sees_all=False)


async def counts(connection: psycopg.AsyncConnection) -> tuple[int, ...]:
    cursor = await connection.execute(
        "SELECT (SELECT count(*) FROM node), (SELECT count(*) FROM statement), (SELECT count(*) FROM anchor),"
        " (SELECT count(*) FROM entity WHERE kind IN ('node', 'statement', 'anchor'))"
    )
    found = await cursor.fetchone()
    assert found is not None
    return tuple(found)


async def test_a_subtree_is_written_and_read_back_as_a_tree_in_its_order(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    root = await write_subtree(connection, document.id, AREA)

    tree = await read_tree(connection, owner(document), document.id)

    assert tree is not None
    [area] = tree
    assert (area.id, area.position, area.node_type_iri, area.original_title) == (
        root,
        1,
        SCHOOL + "Inhaltsbereich",
        "Zahlen und Operationen",
    )
    assert [(child.position, child.code) for child in area.children] == [(1, "1"), (2, "2")]
    first, second = area.children[0].statements
    assert (first.position, first.verbatim, first.text_hash) == (
        1,
        "Die Lernenden rechnen im Kopf.",
        text_hash("Die Lernenden rechnen im Kopf."),
    )
    assert first.addressees == (CV + "addr_educator", CV + "addr_learner")
    assert (second.position, second.subkind_iri) == (2, None)


async def test_a_subtree_s_anchors_are_kept_with_their_blocks(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await write_subtree(connection, document.id, AREA)

    cursor = await connection.execute(
        "SELECT a.page_start, array_agg(b.block_id ORDER BY b.block_id) FROM anchor a"
        " JOIN anchor_block b ON b.anchor_id = a.id JOIN statement s ON s.id = a.statement_id"
        " WHERE s.verbatim = %s GROUP BY a.id",
        ("Die Lernenden rechnen im Kopf.",),
    )
    assert await cursor.fetchall() == [(1, ["p1-b1", "p2-b1"])]
    assert await counts(connection) == (3, 2, 3, 8)


async def test_a_wording_not_found_is_kept_with_its_page_and_no_block(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    missed = AnchorDraft(block_ids=(), page_start=2, match_kind=CV + "match_notFound")

    await write_subtree(
        connection, document.id, node(statements=(statement("Sie lesen.", anchors=(missed,)),))
    )

    cursor = await connection.execute(
        "SELECT a.page_start, a.match_kind_iri, (SELECT count(*) FROM anchor_block) FROM anchor a"
    )
    assert await cursor.fetchall() == [(2, CV + "match_notFound", 0)]


async def test_a_second_subtree_takes_the_next_place(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    first = await write_subtree(connection, document.id, AREA)
    await write_subtree(connection, document.id, node())
    under = await write_subtree(connection, document.id, node("fn_unit", code="3"), parent_id=first)

    tree = await read_tree(connection, owner(document), document.id)

    assert tree is not None
    assert [top.position for top in tree] == [1, 2]
    assert [(child.id, child.position) for child in tree[0].children][-1] == (under, 3)


@pytest.mark.parametrize(
    ("draft", "problem"),
    [
        (
            node(children=(node("fn_unit", children=(node("fn_unit", node_type=VOCATIONAL + "Lernfeld"),)),)),
            "not_in_profile",
        ),
        (node("fn_unit", node_type=SCHOOL + "Inhaltsbereich"), "wrong_core"),
        (
            node(
                statements=(
                    statement("Inhalt", kind=CV + "kind_content", subkind=SCHOOL + "Kompetenzerwartung"),
                )
            ),
            "wrong_core",
        ),
    ],
    ids=["node-type-of-another-profile", "node-type-under-another-function", "subkind-under-another-kind"],
)
async def test_a_subtree_with_a_value_its_profile_does_not_hold_is_written_not_at_all(
    connection: psycopg.AsyncConnection, document: Any, draft: NodeDraft, problem: str
) -> None:
    with pytest.raises(ProfileValueError) as refused:
        await write_subtree(connection, document.id, draft)

    assert refused.value.problem == problem
    assert await counts(connection) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("retired", "draft"),
    [
        ("addr_educator", AREA),  # a statement's addressee, two levels down
        ("match_exact", node(anchors=(AnchorDraft(("p1-b1",), 1, match_kind=CV + "match_exact"),))),
        ("obl_binding", node(statements=(statement("Sie lesen.", obligation=CV + "obl_binding"),))),
    ],
    ids=["addressee", "match-kind-of-a-node-s-anchor", "obligation-of-a-statement"],
)
async def test_a_subtree_with_a_retired_core_value_is_written_not_at_all(
    connection: psycopg.AsyncConnection, document: Any, retired: str, draft: NodeDraft
) -> None:
    await connection.execute("UPDATE vocab_concept SET retired_in = 1 WHERE iri = %s", (CV + retired,))

    with pytest.raises(ProfileValueError) as refused:
        await write_subtree(connection, document.id, draft)

    assert (refused.value.problem, refused.value.value) == ("retired", CV + retired)
    assert await counts(connection) == (0, 0, 0, 0)


async def test_what_a_run_writes_names_the_run(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    with psycopg.connect(url, autocommit=True) as sync:
        run = add_run(sync, document.id)

    await write_subtree(connection, document.id, AREA, run_id=run)

    cursor = await connection.execute(
        "SELECT (SELECT array_agg(DISTINCT run_id) FROM node),"
        " (SELECT array_agg(DISTINCT run_id) FROM statement)"
    )
    assert await cursor.fetchone() == ([run], [run])


async def test_a_subtree_waits_for_another_write_to_its_document_s_tree(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as other, other.transaction():
        await lock_tree(other, document.id)  # as an editor moving a node holds it
        await connection.execute("SET lock_timeout = '200ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            await write_subtree(connection, document.id, node())


async def test_a_node_moved_waits_for_a_write_to_its_document_s_tree(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    # the tree's lock and the one the database's check of a move takes are one
    root = await write_subtree(connection, document.id, node())
    moved = await write_subtree(connection, document.id, node())

    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as other, other.transaction():
        await lock_tree(other, document.id)
        await connection.execute("SET lock_timeout = '200ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            await connection.execute("UPDATE node SET parent_id = %s WHERE id = %s", (root, moved))


async def test_a_subtree_that_waited_for_the_tree_takes_the_place_after_what_was_written_meanwhile(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    async with (
        await psycopg.AsyncConnection.connect(url, autocommit=True) as other,
        await psycopg.AsyncConnection.connect(url, autocommit=True) as watcher,
    ):
        waiting: asyncio.Task[uuid.UUID] | None = None
        try:
            async with other.transaction():
                await lock_tree(other, document.id)
                waiting = asyncio.create_task(write_subtree(connection, document.id, node()))
                await waiting_for_a_lock(watcher, connection.info.backend_pid)
                first = await write_subtree(other, document.id, node())
        finally:  # once the lock is let go, however, the waiting one ends too
            second = None if waiting is None else await waiting

    tree = await read_tree(connection, owner(document), document.id)
    assert tree is not None
    assert [(top.id, top.position) for top in tree] == [(first, 1), (second, 2)]


async def waiting_for_a_lock(watcher: psycopg.AsyncConnection, pid: int) -> None:
    """Until the session of ``pid`` waits for an advisory lock: as long as it is held, it stays."""
    for _ in range(200):
        cursor = await watcher.execute(
            "SELECT count(*) FROM pg_stat_activity"
            " WHERE pid = %s AND wait_event_type = 'Lock' AND wait_event = 'advisory'",
            (pid,),
        )
        found = await cursor.fetchone()
        if found is not None and found[0] > 0:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"session {pid} came to wait for no advisory lock")


async def test_a_tree_is_read_within_a_transaction_already_open(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await write_subtree(connection, document.id, AREA)

    async with connection.transaction():
        tree = await read_tree(connection, owner(document), document.id)

    assert tree is not None and len(tree) == 1


async def test_a_subtree_whose_anchor_names_no_block_of_the_conversion_is_written_not_at_all(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    draft = node(children=(node("fn_unit", statements=(statement("Text", anchors=(anchor("p9-b9"),)),)),))

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        await write_subtree(connection, document.id, draft)

    assert await counts(connection) == (0, 0, 0, 0)


async def test_a_subtree_goes_into_a_document_that_is_one(connection: psycopg.AsyncConnection) -> None:
    with pytest.raises(DocumentError, match="no document"):
        await write_subtree(connection, new_id(), node())


async def test_a_tree_is_read_by_those_who_see_its_document_alone(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await write_subtree(connection, document.id, AREA)

    editor = await read_tree(connection, Reader(new_id(), sees_all=True), document.id)
    stranger = await read_tree(connection, Reader(new_id(), sees_all=False), document.id)
    unknown = await read_tree(connection, owner(document), uuid.uuid4())

    assert editor is not None and len(editor) == 1
    assert (stranger, unknown) == (None, None)


async def test_a_document_without_nodes_has_an_empty_tree(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    assert await read_tree(connection, owner(document), document.id) == ()
