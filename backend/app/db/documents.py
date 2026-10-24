"""The documents of the first layer (plan M1 4.6): made from a register entry's finished
conversion, read by those who may see them - decided here, in SQL.

A document is the account's that made it, and every editor's and admin's to read (``Reader.
sees_all``); whom else it shows itself to - other accounts, visitors - follows with the editor
(plan M1 9, Gesamtplan §7.4.7). It is made of a conversion of its entry's own file, by one who may
read that entry's content, and its rights are the entry's when it is made. Its regions are the
vocabulary's, its document type one of its sector's profile - each chosen only while active
(app/vocab/lookup.py). Which roles may make documents at all is the API's to decide (plan M1 7.5).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.core.ids import new_id
from app.db.source_queries import Reader
from app.db.sources import sector_by_notation
from app.domain.iris import draft_iri
from app.domain.l1 import ProfileProblem
from app.sources.register import EDUCATION_SECTORS
from app.vocab.lookup import REGIONS, profile_concepts

# The one rule of who reads a document, in every query of the first layer (app/db/nodes.py too)
DOCUMENT_VISIBLE = "(d.owner_id = %(me)s OR %(all)s)"
_COLUMNS = """
    d.id, d.source_id, d.conversion_id, d.owner_id, d.work_id, d.draft_iri, d.iri, d.revision, d.frozen_at,
    d.title, d.document_type_iri, d.sector_iri, d.regions, d.rights_status, d.created_at, d.updated_at
"""
_BY_ID = f"SELECT {_COLUMNS} FROM document d WHERE d.id = %(id)s"  # noqa: S608 - fixed parts
_VISIBLE_BY_ID = f"{_BY_ID} AND {DOCUMENT_VISIBLE}"
_VISIBLE = f"""
SELECT {_COLUMNS} FROM document d
WHERE {DOCUMENT_VISIBLE} AND (%(source)s::uuid IS NULL OR d.source_id = %(source)s)
ORDER BY d.created_at DESC, d.id DESC LIMIT %(limit)s
"""  # noqa: S608 - fixed parts
# The entry whose content the maker may read, as app/api/source_content.py has it: its own, every
# entry for the editors, one of no account where its content is open to accounts. Locked, so
# its rights and its conversion stay what the document takes from them
_ENTRY_RIGHTS = """
SELECT s.rights_status FROM source s JOIN conversion c ON c.source_file_id = s.file_id
WHERE s.id = %(source)s AND c.id = %(conversion)s AND c.status = 'done'
    AND (s.owner_id = %(me)s OR %(all)s OR (s.owner_id IS NULL AND %(third_party)s))
FOR SHARE OF s, c
"""
_KNOWN_REGIONS = """
SELECT notation FROM vocab_concept WHERE scheme_iri = %s AND retired_in IS NULL AND notation = ANY(%s)
"""
_INSERT = """
INSERT INTO document (id, source_id, conversion_id, owner_id, draft_iri, sector_scheme, sector_iri, regions,
    rights_status)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


class DocumentError(Exception):
    """A document that cannot be made or changed as asked: its conversion, sector or id. ``code``
    says why it was not made, for an answer that never compares words: ``no_conversion``,
    ``unknown_sector`` or ``unknown_region``; None for a change."""

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ProfileValueError(ValueError):
    """A value the document may not take: a profile value that is none of its profile's or under
    another core value, or a core value retired from the vocabularies."""

    def __init__(self, problem: ProfileProblem | Literal["retired"], value: str) -> None:
        super().__init__(f"{value}: {problem}")
        self.problem = problem
        self.value = value


@dataclass(frozen=True)
class Document:
    id: UUID
    source_id: UUID
    conversion_id: UUID
    owner_id: UUID
    work_id: UUID | None
    draft_iri: str
    iri: str | None
    revision: int
    frozen_at: datetime | None
    title: str | None
    document_type_iri: str | None
    sector_iri: str
    regions: tuple[str, ...]
    rights_status: str
    created_at: datetime
    updated_at: datetime


async def create_document(
    connection: psycopg.AsyncConnection,
    maker: Reader,
    *,
    third_party_content: bool,
    source_id: UUID,
    conversion_id: UUID,
    sector: str,
    regions: Sequence[str] = (),
) -> Document:
    """A new document of ``maker``'s, of the entry's finished conversion, in the sector of this
    notation (``school``) and the regions of these notations (``DE-NW``). ``third_party_content``:
    whether the content of an entry of no account is open to accounts (THIRD_PARTY_MARKDOWN).
    DocumentError where the conversion is none the maker may read, the sector or a region unknown."""
    document_id = new_id()
    regions = list(dict.fromkeys(regions))  # each once, in the order first given
    async with connection.transaction():
        cursor = await connection.execute(
            _ENTRY_RIGHTS,
            {
                "source": source_id,
                "conversion": conversion_id,
                "me": maker.account_id,
                "all": maker.sees_all,
                "third_party": third_party_content,
            },
        )
        entry = await cursor.fetchone()
        if entry is None:  # none, or none the maker may read: alike to the maker
            raise DocumentError("no finished conversion of this entry's file", "no_conversion")
        sector_iri = await sector_by_notation(connection, sector)
        if sector_iri is None:
            raise DocumentError(f"no sector {sector!r}", "unknown_sector")
        cursor = await connection.execute(_KNOWN_REGIONS, (REGIONS, regions))
        unknown = sorted(set(regions) - {row[0] for row in await cursor.fetchall()})
        if unknown:
            raise DocumentError(f"no region {', '.join(unknown)}", "unknown_region")
        await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'document')", (document_id,))
        await connection.execute(
            _INSERT,
            (
                document_id,
                source_id,
                conversion_id,
                maker.account_id,
                draft_iri(document_id),
                EDUCATION_SECTORS,
                sector_iri,
                regions,
                entry[0],
            ),
        )
        await connection.execute("INSERT INTO document_profile (document_id) VALUES (%s)", (document_id,))
        made = await _document(connection, _BY_ID, document_id)
    assert made is not None  # noqa: S101 - written in this transaction
    return made


async def get_document(
    connection: psycopg.AsyncConnection, reader: Reader, document_id: UUID
) -> Document | None:
    """The document, if ``reader`` sees it."""
    return await _document(connection, _VISIBLE_BY_ID, document_id, reader)


async def documents_of(
    connection: psycopg.AsyncConnection, reader: Reader, *, source_id: UUID | None = None, limit: int = 100
) -> list[Document]:
    """The documents ``reader`` sees, of one entry where ``source_id`` names it; the newest first,
    ``limit`` at most."""
    params = {"me": reader.account_id, "all": reader.sees_all, "source": source_id, "limit": limit}
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(_VISIBLE, params)
        rows = await cursor.fetchall()
    return [Document(**{**row, "regions": tuple(row["regions"])}) for row in rows]


async def document_for_job(connection: psycopg.AsyncConnection, document_id: UUID) -> Document | None:
    """The document, for a job that works on it: whom it may be started for is checked when it is
    started (plan M1 7.5), so the job reads it as it stands."""
    return await _document(connection, _BY_ID, document_id)


async def set_document_type(connection: psycopg.AsyncConnection, document_id: UUID, type_iri: str) -> None:
    """Type the document with one of its sector's active document types; ProfileValueError for any
    other, DocumentError for a document that is none."""
    async with connection.transaction():
        cursor = await connection.execute(
            "SELECT s.notation FROM document d JOIN vocab_concept s ON s.iri = d.sector_iri"
            # no key changes: rows naming the document keep their key share meanwhile
            " WHERE d.id = %s FOR NO KEY UPDATE OF d",
            (document_id,),
        )
        found = await cursor.fetchone()
        if found is None:
            raise DocumentError(f"no document {document_id}")
        profile = await profile_concepts(connection, found[0])
        if profile is None or type_iri not in profile.document_types:
            raise ProfileValueError("not_in_profile", type_iri)
        await connection.execute(
            "UPDATE document SET document_type_iri = %s, updated_at = now() WHERE id = %s",
            (type_iri, document_id),
        )


async def _document(
    connection: psycopg.AsyncConnection, query: str, document_id: UUID, reader: Reader | None = None
) -> Document | None:
    params = (
        {"id": document_id, "me": None, "all": True}
        if reader is None
        else {
            "id": document_id,
            "me": reader.account_id,
            "all": reader.sees_all,
        }
    )
    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        row = await cursor.fetchone()
    if row is None:
        return None
    return Document(**{**row, "regions": tuple(row["regions"])})
