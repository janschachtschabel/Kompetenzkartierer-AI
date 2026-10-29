"""A document's work and metadata set by the editors (plan M1 9.6, Paket 9b H3, H4): a work made or one
there is, its issuer, edition and title - under the tree's lock, not beside an open job and not once it is
frozen; issuer, edition and work no more once the document is named by its IRI, which is made of them. A
change of the metadata owes X5 a check (the Kern export carries them)."""

import uuid
from typing import Any

import psycopg
import pytest

from app.db.document_meta import DocumentNamed, ExistingWork, NewWork, set_metadata, set_work
from app.db.documents import DocumentError, create_document
from app.db.editing import DocumentFrozen, JobOpen
from app.db.source_queries import Reader
from app.vocab.form_values import FieldError
from tests.db.test_editing import an_open_job, document, edited_at, one
from tests.db.test_nodes import connection, owner, url

pytestmark = [pytest.mark.pg, pytest.mark.anyio]
__all__ = ["connection", "document", "url"]  # the fixtures, shared with test_editing

IRI = "https://example.org/kk/doc/ministerium/lp-physik/2024"
PHYSICS = NewWork("Lehrplan Physik", "DE-NW", "lp-physik")


async def another(connection: psycopg.AsyncConnection, document: Any) -> Any:
    return await create_document(
        connection, owner(document), third_party_content=False, source_id=document.source_id,
        conversion_id=document.conversion_id, sector="school",
    )  # fmt: skip


async def test_a_work_made_is_the_editor_s_and_the_document_s(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    work = await set_work(connection, owner(document), document.id, PHYSICS)

    assert await one(
        connection,
        "SELECT w.title, w.region, w.short_title, w.owner_id, w.iri, d.work_id = w.id"
        " FROM work w JOIN document d ON d.id = %s WHERE w.id = %s",
        document.id,
        work,
    ) == ("Lehrplan Physik", "DE-NW", "lp-physik", document.owner_id, None, True)
    assert await one(connection, "SELECT kind FROM entity WHERE id = %s", work) == ("work",)


async def test_a_work_there_is_is_set_and_one_there_is_not_refused(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    made = await set_work(connection, owner(document), document.id, PHYSICS)
    assert made is not None
    other = await another(connection, document)

    assert await set_work(connection, owner(document), other.id, ExistingWork(made)) == made
    with pytest.raises(DocumentError) as raised:
        await set_work(connection, owner(document), other.id, ExistingWork(uuid.uuid4()))
    assert raised.value.code == "no_work"
    assert await one(connection, "SELECT count(*) FROM work") == (1,)


async def test_a_work_made_of_what_no_work_may_hold_is_refused_and_none_made(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    # the work's country names its IRI (app/domain/iris.py): one of the vocabulary's, not a typo of one
    for work, problem in (
        (NewWork("Lehrplan\x00Physik", "DE-NW", "lp-physik"), ("title", "not_storable")),
        (NewWork("Lehrplan Physik", "DE-XX", "lp-physik"), ("region", "not_offered")),
    ):
        with pytest.raises(FieldError) as raised:
            await set_work(connection, owner(document), document.id, work)
        assert (raised.value.key, raised.value.problem) == problem
    assert await one(connection, "SELECT count(*) FROM work") == (0,)
    assert await one(connection, "SELECT work_id FROM document WHERE id = %s", document.id) == (None,)


async def test_no_work_is_set_on_a_named_or_frozen_document_or_beside_its_job(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    named, frozen, busy = [await another(connection, document) for _ in range(3)]
    await connection.execute("UPDATE document SET iri = %s WHERE id = %s", (IRI, named.id))
    await connection.execute(
        "UPDATE document SET iri = %s, frozen_at = now() WHERE id = %s", (IRI + "-alt", frozen.id)
    )
    await an_open_job(connection, busy)

    for target, refused in ((named, DocumentNamed), (frozen, DocumentFrozen), (busy, JobOpen)):
        with pytest.raises(refused):
            await set_work(connection, owner(document), target.id, PHYSICS)
    stranger = Reader(uuid.uuid4(), sees_all=False)
    assert await set_work(connection, stranger, document.id, PHYSICS) is None
    assert await one(connection, "SELECT count(*) FROM work") == (0,)


async def test_the_metadata_set_owe_x5_a_check_and_the_same_again_changes_nothing(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    given = {"issuer": "Ministerium für Schule", "edition": "2024", "title": "Kernlehrplan Physik"}

    assert await set_metadata(connection, owner(document), document.id, given) is True
    after = await edited_at(connection, document)
    assert await set_metadata(connection, owner(document), document.id, given) is False
    assert await set_metadata(connection, owner(document), document.id, {"edition": "  "}) is True

    row = await one(connection, "SELECT issuer, edition, title FROM document WHERE id = %s", document.id)
    assert row == ("Ministerium für Schule", None, "Kernlehrplan Physik")  # a blank one is none
    assert after is not None and await edited_at(connection, document) >= after


async def test_a_named_document_keeps_its_issuer_and_edition_and_takes_a_title(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    await connection.execute("UPDATE document SET iri = %s WHERE id = %s", (IRI, document.id))

    for key in ("issuer", "edition"):
        with pytest.raises(DocumentNamed):
            await set_metadata(connection, owner(document), document.id, {key: "Neu"})
    assert await set_metadata(connection, owner(document), document.id, {"title": "Neu"}) is True


async def test_no_metadata_are_set_on_a_frozen_document_or_beside_its_job(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    frozen, busy = [await another(connection, document) for _ in range(2)]
    await connection.execute(
        "UPDATE document SET iri = %s, frozen_at = now() WHERE id = %s", (IRI, frozen.id)
    )
    await an_open_job(connection, busy)

    for target, refused in ((frozen, DocumentFrozen), (busy, JobOpen)):
        with pytest.raises(refused):
            await set_metadata(connection, owner(document), target.id, {"title": "Neu"})
    assert await one(connection, "SELECT count(*) FROM document WHERE title = 'Neu'") == (0,)


async def test_metadata_the_document_may_not_hold_is_refused_and_changes_nothing(
    connection: psycopg.AsyncConnection, document: Any
) -> None:
    for given, problem in (
        ({"issuer": "x" * 501}, ("issuer", "too_long")),
        ({"title": "Op\x00tik"}, ("title", "not_storable")),
        ({"edition": 2024}, ("edition", "not_text")),
        ({"short_title": "lp"}, ("short_title", "unknown")),
    ):
        with pytest.raises(FieldError) as raised:
            await set_metadata(connection, owner(document), document.id, given)
        assert (raised.value.key, raised.value.problem) == problem
    assert await edited_at(connection, document) is None
