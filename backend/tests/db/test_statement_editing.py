"""An editor's changes to a document's statements (plan M1 9.4; Paket 9 G2-G7, app/db/statement_editing.py):
a statement's fields, addressees and anchors set, a statement added after its node's others with an anchor
at least - blocks of the document's conversion, or the page where no block holds it -, a statement taken
away: rejected where a run wrote it, so that no repair proposes it again, deleted where an editor did."""

import uuid
from typing import Any

import psycopg
import pytest

from app.db.documents import create_document
from app.db.editing import DocumentFrozen, JobOpen, NotExtracted, StaleRevision
from app.db.nodes import write_subtree
from app.db.source_queries import Reader
from app.db.statement_editing import HandAnchor, add_statement, drop_or_reject_statement, edit_statement
from app.domain.l1 import AnchorDraft
from app.domain.wording import text_hash
from app.vocab.form_values import FieldError
from tests.db.l1 import add_conversion, add_run
from tests.db.test_editing import a_finding, an_open_job, document, edited_at, one
from tests.db.test_nodes import CV, SCHOOL, connection, node, owner, statement, url

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_nodes

HUMAN, MODEL = CV + "orig_human", CV + "orig_model"
PROPOSED, CONFIRMED, REJECTED = CV + "rev_proposed", CV + "rev_confirmed", CV + "rev_rejected"
LEARNER, EDUCATOR = CV + "addr_learner", CV + "addr_educator"
EXACT, NOT_FOUND = CV + "match_exact", CV + "match_notFound"
NEW = {"verbatim": "Sie prüfen.", "statement_kind": CV + "kind_learningOutcome", "addressees": [LEARNER]}


async def a_run_s_statement(
    url: str, connection: psycopg.AsyncConnection, document: Any, **changes: Any
) -> Any:
    """A statement X4's model wrote, which an editor confirmed, at the end of a node of its own."""
    with psycopg.connect(url, autocommit=True) as sync:
        run = add_run(sync, document.id)
    values: dict[str, Any] = {
        "origin": MODEL,
        "review_status": CONFIRMED,
        "details": {"codeText": "K1"},
    } | changes
    top = await write_subtree(connection, document.id, node(statements=(statement("Sie messen.", **values),)),
                              run_id=run)  # fmt: skip
    return (await one(connection, "SELECT id FROM statement WHERE node_id = %s", top))[0]


async def statement_row(connection: psycopg.AsyncConnection, statement_id: Any) -> tuple[Any, ...]:
    return await one(
        connection,
        "SELECT s.verbatim, s.lead_in, s.statement_kind_iri, s.subkind_iri, s.obligation_iri, s.details,"
        " s.origin_iri, s.review_status_iri, s.text_hash, s.revision,"
        " array(SELECT a.addressee_iri FROM statement_addressee a WHERE a.statement_id = s.id ORDER BY 1)"
        " FROM statement s WHERE s.id = %s",
        statement_id,
    )


async def anchors_of(connection: psycopg.AsyncConnection, statement_id: Any) -> list[tuple[Any, ...]]:
    cursor = await connection.execute(
        "SELECT a.page_start, a.page_end, a.match_kind_iri, a.quote,"
        " array(SELECT ab.block_id FROM anchor_block ab WHERE ab.anchor_id = a.id ORDER BY 1)"
        " FROM anchor a WHERE a.statement_id = %s ORDER BY a.id",
        (statement_id,),
    )
    return [tuple(found) for found in await cursor.fetchall()]


async def test_an_edit_sets_a_statement_s_fields_and_makes_it_an_editor_s_proposal(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    said = await a_run_s_statement(url, connection, document)
    await connection.execute('UPDATE statement SET details = details || \'{"note": "kept"}\'')
    given = {
        "lead_in": "Die Lernenden",
        "codeText": None,
        "levelText": "B",
        "addressees": [EDUCATOR, LEARNER],
    }

    revision = await edit_statement(connection, owner(document), said, 1, given)

    assert revision == 2
    assert await statement_row(connection, said) == (
        "Sie messen.", "Die Lernenden", CV + "kind_learningOutcome", None, None,
        {"levelText": "B", "note": "kept"}, HUMAN, PROPOSED, text_hash("Sie messen."), 2, [EDUCATOR, LEARNER],
    )  # fmt: skip
    assert await one(connection, "SELECT rule_id FROM statement WHERE id = %s", said) == (None,)
    assert await edited_at(connection, document) is not None


async def test_an_edit_that_changes_nothing_leaves_the_statement_as_it_was(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    said = await a_run_s_statement(url, connection, document)
    before = await statement_row(connection, said)
    given = {"verbatim": "Sie messen.", "lead_in": None, "codeText": "K1", "addressees": [LEARNER]}

    assert await edit_statement(connection, owner(document), said, 1, given) == 1

    assert await statement_row(connection, said) == before
    assert await edited_at(connection, document) is None


async def test_a_new_wording_takes_its_hash_and_leaves_the_anchors_unchecked(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    checked = AnchorDraft(block_ids=("p1-b1",), page_start=1, quote="Sie messen.", match_kind=EXACT)
    missed = AnchorDraft(block_ids=(), page_start=2, match_kind=NOT_FOUND)
    said = await a_run_s_statement(url, connection, document, anchors=(checked, missed))

    await edit_statement(connection, owner(document), said, 1, {"lead_in": "Die Lernenden"})
    assert [found[2] for found in await anchors_of(connection, said)] == [EXACT, NOT_FOUND]
    await edit_statement(connection, owner(document), said, 2, {"verbatim": "Sie messen genau."})

    assert (await statement_row(connection, said))[8] == text_hash("Sie messen genau.")
    assert await anchors_of(connection, said) == [
        (1, None, None, None, ["p1-b1"]),
        (2, None, NOT_FOUND, None, []),
    ]


async def test_an_edit_replaces_the_anchors_and_the_findings_on_them_go(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    said = await a_run_s_statement(url, connection, document)
    [(old,)] = await (
        await connection.execute("SELECT id FROM anchor WHERE statement_id = %s", (said,))
    ).fetchall()
    on_anchor, on_statement = (
        await a_finding(connection, document, old),
        await a_finding(connection, document, said),
    )

    await edit_statement(
        connection,
        owner(document),
        said,
        1,
        {},
        anchors=[HandAnchor(blocks=("p2-b1", "p1-b1")), HandAnchor(page=2)],
    )

    assert await anchors_of(connection, said) == [
        (1, 2, None, None, ["p1-b1", "p2-b1"]),  # its pages from its blocks, X5 to check it
        (2, None, NOT_FOUND, None, []),
    ]
    assert await one(connection, "SELECT array_agg(id) FROM validation_finding") == ([on_statement],)
    assert on_anchor != on_statement
    assert (await statement_row(connection, said))[6:] == (
        HUMAN, PROPOSED, text_hash("Sie messen."), 2, [LEARNER],
    )  # fmt: skip


async def test_an_edit_the_statement_may_not_take_changes_nothing(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    said = await a_run_s_statement(url, connection, document)
    before = await statement_row(connection, said)

    with pytest.raises(StaleRevision) as stale:
        await edit_statement(connection, owner(document), said, 2, {"lead_in": "Die Lernenden"})
    assert stale.value.current == 1
    for given, anchors, problem in (
        ({"statement_kind": CV + "kind_content", "subkind": SCHOOL + "Kompetenzerwartung"}, None,
         ("subkind", "not_under")),
        ({"addressees": []}, None, ("addressees", "required")),
        ({}, [], ("anchors", "required")),
        ({}, [HandAnchor(blocks=("p1-b1", "p9-b9"))], ("anchors", "unknown_block")),
        ({}, [HandAnchor()], ("anchors", "no_page")),
        ({}, [HandAnchor(page=0)], ("anchors", "no_page")),
        ({}, [HandAnchor(page=3)], ("anchors", "no_page")),  # the conversion has two
    ):  # fmt: skip
        with pytest.raises(FieldError) as raised:
            await edit_statement(connection, owner(document), said, 1, given, anchors=anchors)
        assert (raised.value.key, raised.value.problem) == problem
    assert await statement_row(connection, said) == before
    assert len(await anchors_of(connection, said)) == 1
    assert await edited_at(connection, document) is None


async def test_an_edit_leaves_the_pair_it_names_not_as_it_stands(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    # as a node's (tests/db/test_editing.py): a subkind the vocabulary no longer puts under its kind
    said = await a_run_s_statement(url, connection, document, subkind=SCHOOL + "Kompetenzerwartung")
    with psycopg.connect(url, autocommit=True) as sync:
        sync.execute(
            "UPDATE vocab_concept SET broader = '{}' WHERE iri = %s", (SCHOOL + "Kompetenzerwartung",)
        )

    assert await edit_statement(connection, owner(document), said, 1, {"lead_in": "Die Lernenden"}) == 2
    row = await one(connection, "SELECT lead_in, subkind_iri FROM statement WHERE id = %s", said)
    assert row == ("Die Lernenden", SCHOOL + "Kompetenzerwartung")


async def test_a_block_of_another_conversion_is_no_anchor_of_the_document(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    said = await a_run_s_statement(url, connection, document)
    with psycopg.connect(url, autocommit=True) as sync:
        other = add_conversion(sync, b"\x05" * 32)["conversion"]
        sync.execute(
            "INSERT INTO document_block (conversion_id, block_id, page, last_page, seq, kind, text,"
            " x0, top, x1, bottom, bold, italic)"
            " VALUES (%s, 'p2-b7', 2, 2, 3, 'text', 'Text', 0, 0, 1, 1, false, false)",
            (other,),
        )

    with pytest.raises(FieldError) as raised:
        await edit_statement(
            connection, owner(document), said, 1, {}, anchors=[HandAnchor(blocks=("p2-b7",))]
        )

    assert (raised.value.key, raised.value.problem) == ("anchors", "unknown_block")
    assert len(await anchors_of(connection, said)) == 1


async def test_a_new_statement_goes_after_the_node_s_others_as_an_editor_s_proposal(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top = await write_subtree(
        connection, document.id, node(statements=(statement("Sie lesen."), statement("Sie rechnen.")))
    )
    given = NEW | {"lead_in": "Die Lernenden", "subkind": SCHOOL + "Kompetenzerwartung", "codeText": "K2"}

    made = await add_statement(connection, owner(document), top, given, [HandAnchor(blocks=("p2-b1",))])

    assert made is not None
    assert await one(connection, "SELECT node_id, position, run_id FROM statement WHERE id = %s", made) == (
        top, 3, None,
    )  # fmt: skip
    assert await statement_row(connection, made) == (
        "Sie prüfen.", "Die Lernenden", CV + "kind_learningOutcome", SCHOOL + "Kompetenzerwartung", None,
        {"codeText": "K2"}, HUMAN, PROPOSED, text_hash("Sie prüfen."), 1, [LEARNER],
    )  # fmt: skip
    assert await anchors_of(connection, made) == [(2, None, None, None, ["p2-b1"])]
    assert await edited_at(connection, document) is not None


async def test_a_new_statement_has_its_form_s_fields_and_an_anchor(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    top = await write_subtree(connection, document.id, node())

    for given, anchors, problem in (
        (NEW, [], ("anchors", "required")),
        ({"statement_kind": CV + "kind_learningOutcome", "addressees": [LEARNER]}, [HandAnchor(page=1)],
         ("verbatim", "required")),
        ({"verbatim": "Sie prüfen.", "statement_kind": CV + "kind_learningOutcome"}, [HandAnchor(page=1)],
         ("addressees", "required")),
    ):  # fmt: skip
        with pytest.raises(FieldError) as raised:
            await add_statement(connection, owner(document), top, given, anchors)
        assert (raised.value.key, raised.value.problem) == problem
    assert await one(connection, "SELECT count(*) FROM statement") == (0,)


async def test_a_run_s_statement_is_rejected_and_an_editor_s_deleted(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    by_run = await a_run_s_statement(url, connection, document)
    edited = await a_run_s_statement(url, connection, document)
    await edit_statement(
        connection, owner(document), edited, 1, {"lead_in": "Die Lernenden"}
    )  # now the editor's
    top = await write_subtree(connection, document.id, node())
    by_hand = await add_statement(connection, owner(document), top, NEW, [HandAnchor(page=1)])
    assert by_hand is not None
    on_hand = await a_finding(connection, document, by_hand)
    on_run = await a_finding(connection, document, by_run)
    await connection.execute("UPDATE document SET edited_at = NULL")

    assert await drop_or_reject_statement(connection, owner(document), by_run, 1) == "rejected"
    assert await edited_at(connection, document) is not None
    assert await drop_or_reject_statement(connection, owner(document), edited, 2) == "rejected"
    assert await drop_or_reject_statement(connection, owner(document), by_hand, 1) == "deleted"

    assert (await statement_row(connection, by_run))[6:10] == (MODEL, REJECTED, text_hash("Sie messen."), 2)
    assert (await statement_row(connection, edited))[6:10] == (HUMAN, REJECTED, text_hash("Sie messen."), 3)
    assert await one(connection, "SELECT count(*) FROM statement WHERE id = %s", by_hand) == (0,)
    assert await one(connection, "SELECT array_agg(id) FROM validation_finding") == ([on_run],)
    assert on_hand != on_run
    # a statement rejected stays so: taking it away again changes nothing
    assert await drop_or_reject_statement(connection, owner(document), by_run, 2) == "rejected"
    assert (await statement_row(connection, by_run))[9] == 2


async def test_a_model_s_statement_no_run_names_is_rejected_too(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    # as in a draft copy (plan M1 9.6), which keeps no runs: the origin alone tells the model's
    top = await write_subtree(
        connection, document.id, node(statements=(statement("Sie lesen.", origin=MODEL),))
    )
    said = (await one(connection, "SELECT id FROM statement WHERE node_id = %s", top))[0]

    assert await drop_or_reject_statement(connection, owner(document), said, 1) == "rejected"

    assert (await statement_row(connection, said))[6:8] == (MODEL, REJECTED)


async def test_no_statement_is_added_before_the_extraction_has_read_every_package(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    # an open package of X4 begins at position 1 of its node: a hand-written statement there would meet it
    other = await create_document(
        connection, owner(document), third_party_content=False, source_id=document.source_id,
        conversion_id=document.conversion_id, sector="school",
    )  # fmt: skip
    top = await write_subtree(connection, other.id, node())

    with pytest.raises(NotExtracted):
        await add_statement(connection, owner(document), top, NEW, [HandAnchor(page=1)])
    assert await one(connection, "SELECT count(*) FROM statement") == (0,)


async def test_no_statement_is_changed_beside_an_open_job_or_of_a_frozen_document(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    said = await a_run_s_statement(url, connection, document)
    top = (await one(connection, "SELECT node_id FROM statement WHERE id = %s", said))[0]

    def changes() -> list[Any]:
        return [
            lambda: edit_statement(connection, owner(document), said, 1, {"lead_in": "Die Lernenden"}),
            lambda: add_statement(connection, owner(document), top, NEW, [HandAnchor(page=1)]),
            lambda: drop_or_reject_statement(connection, owner(document), said, 1),
        ]

    job = await an_open_job(connection, document)
    for change in changes():
        with pytest.raises(JobOpen) as raised:
            await change()
        assert raised.value.job_id == job
    await connection.execute("UPDATE job SET status = 'done', finished_at = now() WHERE id = %s", (job,))
    await connection.execute(
        "UPDATE document SET iri = 'https://example.org/curriculum/1', frozen_at = now() WHERE id = %s",
        (document.id,),
    )
    for change in changes():
        with pytest.raises(DocumentFrozen):
            await change()
    assert await one(connection, "SELECT count(*), max(revision) FROM statement") == (1, 1)


async def test_a_statement_is_none_to_who_sees_not_its_document(
    url: str, connection: psycopg.AsyncConnection, document: Any
) -> None:
    said = await a_run_s_statement(url, connection, document)
    top = (await one(connection, "SELECT node_id FROM statement WHERE id = %s", said))[0]
    stranger = Reader(uuid.uuid4(), sees_all=False)

    assert await edit_statement(connection, stranger, said, 1, {"lead_in": "Die Lernenden"}) is None
    assert await add_statement(connection, stranger, top, NEW, [HandAnchor(page=1)]) is None
    assert await drop_or_reject_statement(connection, stranger, said, 1) is None
    assert await edit_statement(connection, owner(document), uuid.uuid4(), 1, {"lead_in": "Die"}) is None
    assert await add_statement(connection, owner(document), uuid.uuid4(), NEW, [HandAnchor(page=1)]) is None
    assert (await statement_row(connection, said))[9] == 1
