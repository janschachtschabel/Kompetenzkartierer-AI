"""Documents of the first layer (plan M1 4.6): made from an entry's finished conversion, read by
those who may see them - in SQL - and typed only from their sector's profile."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.core.ids import new_id
from app.db.documents import (
    DocumentError,
    ProfileValueError,
    create_document,
    documents_of,
    get_document,
    set_document_type,
)
from app.db.migrate import migrate
from app.db.source_queries import Reader
from app.vocab.loader import read_vocabulary
from app.vocab.lookup import REGIONS
from app.vocab.store import load_vocabulary
from tests.db.l1 import add_conversion, add_node

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
SCHOOL = "https://w3id.org/wlo/curriculum/profile/school#"
VOCATIONAL = "https://w3id.org/wlo/curriculum/profile/vocational#"


@pytest.fixture
def url(database_url: str) -> str:
    migrate(database_url)
    load_vocabulary(database_url, read_vocabulary(ONTOLOGY))
    return database_url


@pytest.fixture
def made(url: str) -> dict[str, uuid.UUID]:
    with psycopg.connect(url, autocommit=True) as connection:
        made = add_conversion(connection)
        connection.execute(
            "UPDATE source SET rights_status = 'amtlich', rights_evidence = 'Amtsblatt 7/2023' WHERE id = %s",
            (made["source"],),
        )
        return made


@pytest.fixture
async def connection(url: str) -> AsyncIterator[psycopg.AsyncConnection]:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as opened:
        yield opened


async def make(
    connection: psycopg.AsyncConnection,
    made: dict[str, uuid.UUID],
    reader: Reader | None = None,
    **changes: Any,
) -> Any:
    values: dict[str, Any] = {
        "third_party_content": False,
        "source_id": made["source"],
        "conversion_id": made["conversion"],
        "sector": "school",
        "regions": ("DE-NW",),
    } | changes
    return await create_document(connection, reader or Reader(made["owner"], sees_all=False), **values)


async def test_a_document_is_made_of_an_entry_whose_content_its_maker_may_read(
    url: str, connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    editor = Reader(new_id(), sees_all=True)
    with psycopg.connect(url, autocommit=True) as sync:
        sync.execute("INSERT INTO account (id, name) VALUES (%s, 'redaktion-1')", (editor.account_id,))
        seed = add_conversion(sync, b"\x02" * 32)
        sync.execute(
            "UPDATE source SET owner_id = NULL, provenance = 'recherche' WHERE id = %s", (seed["source"],)
        )

    with pytest.raises(DocumentError, match="conversion"):
        await make(connection, made, Reader(seed["owner"], sees_all=False))  # another account's upload
    with pytest.raises(DocumentError, match="conversion"):
        await make(connection, seed)  # a seed's content, while it is hidden from accounts
    by_editor = await make(connection, made, editor)
    of_seed = await make(connection, seed, third_party_content=True)

    assert (by_editor.owner_id, of_seed.owner_id) == (editor.account_id, seed["owner"])


async def test_the_documents_a_reader_sees_are_listed_newest_first(
    url: str, connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    first, second = await make(connection, made), await make(connection, made)
    with psycopg.connect(url, autocommit=True) as sync:
        other = add_conversion(sync, b"\x03" * 32)
    theirs = await make(connection, other)
    owner, editor = Reader(made["owner"], sees_all=False), Reader(new_id(), sees_all=True)

    listed = {
        "own": await documents_of(connection, owner),
        "all": await documents_of(connection, editor),
        "of_source": await documents_of(connection, editor, source_id=other["source"]),
        "capped": await documents_of(connection, owner, limit=1),
    }

    assert {name: [found.id for found in documents] for name, documents in listed.items()} == {
        "own": [second.id, first.id],
        "all": [theirs.id, second.id, first.id],
        "of_source": [theirs.id],
        "capped": [second.id],
    }


async def test_a_document_refused_says_why_by_its_code(
    connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    # the API answers by the code, never by the words
    refusals: list[dict[str, Any]] = [
        {"reader": Reader(new_id(), sees_all=False)},  # an entry the maker may not read
        {"sector": "kindergarten"},
        {"regions": ("DE-NW", "ZZ")},
    ]
    codes = []
    for refusal in refusals:
        reader = refusal.pop("reader", None)
        with pytest.raises(DocumentError) as refused:
            await make(connection, made, reader, **refusal)
        codes.append(refused.value.code)

    assert codes == ["no_conversion", "unknown_sector", "unknown_region"]


async def test_a_document_s_regions_are_regions_the_vocabulary_holds_each_once(
    connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    document = await make(connection, made, regions=("DE-NW", "DE-BY", "DE-NW"))

    assert document.regions == ("DE-NW", "DE-BY")
    with pytest.raises(DocumentError, match="region"):
        await make(connection, made, regions=("DE-NW", "ZZ"))
    await connection.execute(
        "UPDATE vocab_concept SET retired_in = 1 WHERE scheme_iri = %s AND notation = 'DE-NW'", (REGIONS,)
    )
    with pytest.raises(DocumentError, match="region"):
        await make(connection, made)  # of a region retired


async def test_a_document_takes_its_entry_s_rights_once_a_change_to_them_is_done(
    url: str, connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    with psycopg.connect(url) as editor:  # in a transaction of its own until it ends
        editor.execute("UPDATE source SET rights_status = 'unklar' WHERE id = %s", (made["source"],))
        await connection.execute("SET lock_timeout = '200ms'")
        with pytest.raises(psycopg.errors.LockNotAvailable):
            await make(connection, made)
        editor.rollback()


async def test_a_document_is_made_from_its_entry_s_finished_conversion_with_the_entry_s_rights(
    connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    document = await make(connection, made)

    assert (document.draft_iri, document.revision, document.rights_status, document.regions) == (
        document.id.urn,
        1,
        "amtlich",
        ("DE-NW",),
    )
    assert document.sector_iri.endswith("#sec_school")
    cursor = await connection.execute(
        "SELECT term_mappings FROM document_profile WHERE document_id = %s", (document.id,)
    )
    assert await cursor.fetchone() == ([],)


async def test_a_document_is_made_of_no_conversion_but_its_entry_s_finished_one(
    url: str, connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    with psycopg.connect(url, autocommit=True) as sync:
        other = add_conversion(sync, b"\x02" * 32)
        sync.execute(
            "UPDATE conversion SET status = 'pending', finished_at = NULL, pages = NULL WHERE id = %s",
            (other["conversion"],),
        )

    with pytest.raises(DocumentError, match="conversion"):
        await make(connection, made, conversion_id=other["conversion"])  # another file's
    with pytest.raises(DocumentError, match="conversion"):
        await make(connection, other)  # not finished
    with pytest.raises(DocumentError, match="sector"):
        await make(connection, made, sector="kindergarten")
    cursor = await connection.execute(
        "SELECT (SELECT count(*) FROM document), (SELECT count(*) FROM entity WHERE kind = 'document')"
    )
    assert await cursor.fetchone() == (0, 0)


async def test_a_document_is_seen_by_its_owner_and_the_editors_alone(
    connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    document = await make(connection, made)

    owner = await get_document(connection, Reader(made["owner"], sees_all=False), document.id)
    editor = await get_document(connection, Reader(new_id(), sees_all=True), document.id)
    stranger = await get_document(connection, Reader(new_id(), sees_all=False), document.id)
    unknown = await get_document(connection, Reader(made["owner"], sees_all=True), new_id())

    assert owner == editor == document
    assert (stranger, unknown) == (None, None)


async def test_a_document_s_type_comes_from_its_sector_s_profile(
    connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    document = await make(connection, made)

    await set_document_type(connection, document.id, SCHOOL + "dt-Lehrplan")
    typed = await get_document(connection, Reader(made["owner"], sees_all=False), document.id)

    assert typed is not None and typed.document_type_iri == SCHOOL + "dt-Lehrplan"
    with pytest.raises(ProfileValueError) as refused:
        await set_document_type(connection, document.id, VOCATIONAL + "dt-Rahmenlehrplan")
    assert refused.value.problem == "not_in_profile"


async def test_a_document_is_typed_while_its_nodes_are_written(
    url: str, connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    # a node written names its document with a key share; typing it changes no key, so neither waits
    document = await make(connection, made)

    with psycopg.connect(url, autocommit=True) as writer, writer.transaction():
        add_node(writer, document.id)
        await connection.execute("SET lock_timeout = '200ms'")
        await set_document_type(connection, document.id, SCHOOL + "dt-Lehrplan")


async def test_a_retired_document_type_is_chosen_no_more(
    connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID]
) -> None:
    document = await make(connection, made)
    await connection.execute(
        "UPDATE vocab_concept SET retired_in = 1 WHERE iri = %s", (SCHOOL + "dt-Lehrplan",)
    )

    with pytest.raises(ProfileValueError):
        await set_document_type(connection, document.id, SCHOOL + "dt-Lehrplan")


async def test_an_unknown_document_takes_no_type(connection: psycopg.AsyncConnection) -> None:
    with pytest.raises(DocumentError, match="no document"):
        await set_document_type(connection, new_id(), SCHOOL + "dt-Lehrplan")
