"""Reading the register (plan M1, 1.9): who sees which entry is decided here, in SQL.

An account sees its own entries and those of no account (seed, research) as metadata; editors and
admins see every entry. A search term is matched as written: its ``%`` and ``_`` are signs.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

# The one rule of who sees an entry, in every query of the register
_VISIBLE = "(s.owner_id = %(me)s OR s.owner_id IS NULL OR %(all)s)"
_COLUMNS = """
    s.id, s.title, s.provenance, s.rights_status, s.source_type, s.register_status, s.country,
    s.sector_iri, s.url, s.license, s.rights_evidence, s.owner_id, s.created_at, s.updated_at,
    s.file_name, s.mime, f.size_bytes, f.sha256, f.storage_key
"""


@dataclass(frozen=True)
class Reader:
    account_id: UUID
    sees_all: bool  # editors and admins


@dataclass(frozen=True)
class Filters:
    status: str | None = None
    provenance: str | None = None
    country: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class Acquisition:
    method: str
    acquired_at: datetime
    chain: list[str]
    received_name: str | None


def _like(text: str) -> str:
    """``text`` as a LIKE pattern that matches it anywhere, its wildcards escaped."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def list_sources(
    connection: psycopg.AsyncConnection, reader: Reader, filters: Filters, *, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """A page of the entries ``reader`` sees, newest first, and how many there are in all."""
    where = [_VISIBLE]
    values: dict[str, Any] = {
        "me": reader.account_id,
        "all": reader.sees_all,
        "limit": limit,
        "offset": offset,
    }
    if filters.status is not None:
        where.append("s.register_status = %(status)s")
        values["status"] = filters.status
    if filters.provenance is not None:
        where.append("s.provenance = %(provenance)s")
        values["provenance"] = filters.provenance
    if filters.country is not None:
        where.append("s.country = %(country)s")
        values["country"] = filters.country
    if filters.text:
        where.append("(s.title ILIKE %(pattern)s OR s.url ILIKE %(pattern)s)")
        values["pattern"] = _like(filters.text)
    condition = " AND ".join(where)
    cursor = connection.cursor(row_factory=dict_row)
    await cursor.execute(
        f"SELECT {_COLUMNS} FROM source s LEFT JOIN source_file f ON f.id = s.file_id"  # noqa: S608 - fixed parts
        f" WHERE {condition} ORDER BY s.created_at DESC, s.id DESC LIMIT %(limit)s OFFSET %(offset)s",
        values,
    )
    entries = await cursor.fetchall()
    counted = await connection.execute(f"SELECT count(*) FROM source s WHERE {condition}", values)  # noqa: S608
    found = await counted.fetchone()
    return entries, int(found[0]) if found else 0


async def ownerless_source(connection: psycopg.AsyncConnection, source_id: UUID) -> dict[str, Any] | None:
    """The entry, if it is of no account (seed, research): what a visitor may get at most."""
    cursor = connection.cursor(row_factory=dict_row)
    await cursor.execute(
        f"SELECT {_COLUMNS} FROM source s LEFT JOIN source_file f ON f.id = s.file_id"  # noqa: S608 - fixed parts
        " WHERE s.id = %s AND s.owner_id IS NULL",
        (source_id,),
    )
    return await cursor.fetchone()


async def get_source(
    connection: psycopg.AsyncConnection, reader: Reader, source_id: UUID, *, for_update: bool = False
) -> tuple[dict[str, Any], list[Acquisition]] | None:
    """The entry with how its file came, if ``reader`` sees it. ``for_update`` locks its row to
    the end of the caller's transaction: a change checked against the entry as read is then
    written to that entry, not to one another change wrote in between."""
    lock = " FOR UPDATE OF s" if for_update else ""
    cursor = connection.cursor(row_factory=dict_row)
    await cursor.execute(
        f"SELECT {_COLUMNS} FROM source s LEFT JOIN source_file f ON f.id = s.file_id"  # noqa: S608 - fixed parts
        f" WHERE s.id = %(id)s AND {_VISIBLE}{lock}",
        {"id": source_id, "me": reader.account_id, "all": reader.sees_all},
    )
    entry = await cursor.fetchone()
    if entry is None:
        return None
    found = await connection.execute(
        "SELECT method, acquired_at, chain, received_name FROM acquisition"
        " WHERE source_id = %s ORDER BY acquired_at",
        (source_id,),
    )
    return entry, [Acquisition(*row) for row in await found.fetchall()]


async def seed_of(
    connection: psycopg.AsyncConnection, source_id: UUID
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """What a seed or research row said of the entry, and the access notes of its land, school
    form and subject (migrations 0008, 0009); nothing for an entry no dataset seeded."""
    cursor = connection.cursor(row_factory=dict_row)
    await cursor.execute(
        "SELECT dataset, school_form, stage, subject_key, subject, grade_from, grade_to, binding,"
        " archive_url, archived_at, evidence FROM source_seed WHERE source_id = %s",
        (source_id,),
    )
    seed = await cursor.fetchone()
    if seed is None:
        return None, []
    await cursor.execute(
        "SELECT n.categories, n.field, n.text, n.url, n.origin FROM access_note n"
        " JOIN source s ON s.id = %s JOIN source_seed x ON x.source_id = s.id"
        " WHERE n.country = s.country AND n.school_form = x.school_form AND n.subject = x.subject"
        " ORDER BY n.text",
        (source_id,),
    )
    return seed, await cursor.fetchall()
