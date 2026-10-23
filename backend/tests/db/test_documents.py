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
    get_document,
    set_document_type,
)
from app.db.migrate import migrate
from app.db.source_queries import Reader
from app.vocab.loader import read_vocabulary
from app.vocab.store import load_vocabulary
from tests.db.l1 import add_conversion

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


async def make(connection: psycopg.AsyncConnection, made: dict[str, uuid.UUID], **changes: Any) -> Any:
    values: dict[str, Any] = {
        "owner_id": made["owner"],
        "source_id": made["source"],
        "conversion_id": made["conversion"],
        "sector": "school",
        "regions": ("DE-NW",),
    } | changes
    return await create_document(connection, **values)


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
