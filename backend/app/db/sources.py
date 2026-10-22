"""The source register in the database (migration 0006_sources).

A file is one ``source_file`` row per SHA-256, shared by every source that holds those bytes;
who may see what is decided at ``source``.
"""

from dataclasses import dataclass
from uuid import UUID

import psycopg

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
