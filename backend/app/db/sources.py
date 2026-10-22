"""The source register in the database (migration 0006_sources).

A file is one ``source_file`` row per SHA-256, shared by every source that holds those bytes;
who may see what is decided at ``source``.
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.core.ids import new_id


@dataclass(frozen=True)
class StoredFile:
    """Bytes as the store holds them."""

    sha256: bytes
    size: int
    mime: str
    storage_key: str


async def file_row(connection: psycopg.AsyncConnection, stored: StoredFile) -> UUID:
    """The ``source_file`` of these bytes, made if none is. Two uploads of the same bytes at once:
    the second insert waits for the first and does nothing, then finds its row."""
    cursor = await connection.execute(
        "INSERT INTO source_file (id, sha256, size_bytes, mime, storage_key) VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT (sha256) DO NOTHING RETURNING id",
        (new_id(), stored.sha256, stored.size, stored.mime, stored.storage_key),
    )
    made = await cursor.fetchone()
    if made is not None:
        return UUID(str(made[0]))
    cursor = await connection.execute("SELECT id FROM source_file WHERE sha256 = %s", (stored.sha256,))
    found = await cursor.fetchone()
    assert found is not None  # noqa: S101 - the conflict was with this row
    return UUID(str(found[0]))


@dataclass(frozen=True)
class FetchTarget:
    """What source.fetch needs of an entry."""

    url: str | None
    owner_id: UUID | None


async def fetch_target(connection: psycopg.AsyncConnection, source_id: UUID) -> FetchTarget | None:
    cursor = await connection.execute("SELECT url, owner_id FROM source WHERE id = %s", (source_id,))
    found = await cursor.fetchone()
    return None if found is None else FetchTarget(url=found[0], owner_id=found[1])


async def set_register_status(connection: psycopg.AsyncConnection, source_id: UUID, status: str) -> None:
    """What a check or a fetch found out about an entry that has no file yet."""
    await connection.execute(
        "UPDATE source SET register_status = %s, updated_at = now() WHERE id = %s AND file_id IS NULL",
        (status, source_id),
    )


async def record_fetch(
    connection: psycopg.AsyncConnection,
    *,
    source_id: UUID,
    account_id: UUID | None,
    stored: StoredFile,
    file_name: str,
    received_name: str,
    chain: list[str],
    title: str,
) -> None:
    """The entry acquired with the file its URL gave; ``title`` names it if it had none."""
    async with connection.transaction():
        file_id = await file_row(connection, stored)
        await connection.execute(
            "UPDATE source SET register_status = 'acquired', file_id = %s, file_name = %s,"
            " title = CASE WHEN title = '' THEN %s ELSE title END, updated_at = now() WHERE id = %s",
            (file_id, file_name, title, source_id),
        )
        await connection.execute(
            "INSERT INTO acquisition (id, source_id, file_id, method, account_id, chain, received_name)"
            " VALUES (%s, %s, %s, 'url', %s, %s, %s)",
            (new_id(), source_id, file_id, account_id, Jsonb(chain), received_name),
        )


async def record_upload(
    connection: psycopg.AsyncConnection,
    *,
    owner: UUID,
    stored: StoredFile,
    file_name: str,
    received_name: str,
    title: str,
) -> UUID:
    """A new source of ``owner``, acquired with its file by upload; its id."""
    source_id = new_id()
    async with connection.transaction():
        file_id = await file_row(connection, stored)
        await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (source_id,))
        await connection.execute(
            "INSERT INTO source (id, owner_id, provenance, title, register_status, file_id, file_name)"
            " VALUES (%s, %s, 'upload', %s, 'acquired', %s, %s)",
            (source_id, owner, title, file_id, file_name),
        )
        await connection.execute(
            "INSERT INTO acquisition (id, source_id, file_id, method, account_id, received_name)"
            " VALUES (%s, %s, %s, 'upload', %s, %s)",
            (new_id(), source_id, file_id, owner, received_name),
        )
    return source_id
