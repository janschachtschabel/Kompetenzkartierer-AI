"""A document's work and metadata, set by the editors before it is frozen (plan M1 9.6; Paket 9b H3, H4).

The work is one there is or one made of a title, a country and a short title; the metadata are the
issuer, the edition and the title X1 read off the document, as an editor puts them right. Both wait for
the tree's lock and refuse a frozen document and one beside its open job (``guard_document``); the
metadata also one X4 has not read yet (``guard``, NotExtracted): an extraction to come would write them
over with what X1 reads, the work it leaves. A document named by its IRI - frozen once, or a draft
copy of one - keeps its work, issuer and edition, which the IRI is made of (``DocumentNamed``); its
title it may change. A change of the metadata owes X5 a check: the Kern export carries them.

simplify: who sees a document edits its metadata, as its tree (app/db/editing.py); the work is the
editors' alone, which the API asks (app/api/document_meta.py).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

import psycopg
from psycopg import sql

from app.db.anchors import new_entity
from app.db.documents import DocumentError, unknown_regions
from app.db.editing import DOCUMENT, guard, guard_document, mark_edited, target_of
from app.db.source_queries import Reader
from app.domain.text import UNSTORABLE
from app.vocab.form_values import FieldError

# the longest each may be, as the table's checks have it (migration l1_documents)
METADATA: Final = {"title": 1000, "issuer": 500, "edition": 200}
# what the document's IRI is made of: fixed once it has one
_NAMING = frozenset({"issuer", "edition"})


class DocumentNamed(Exception):
    """The document has its IRI already: what it is made of stays."""


@dataclass(frozen=True)
class ExistingWork:
    work_id: UUID


@dataclass(frozen=True)
class NewWork:
    title: str
    region: str  # ISO 3166-1 or -2: "DE", "DE-NW"
    short_title: str  # a slug: "lp-physik"


async def set_work(
    connection: psycopg.AsyncConnection, reader: Reader, document_id: UUID, work: ExistingWork | NewWork
) -> UUID | None:
    """Set the document's work - one there is, or one made, ``reader``'s; the work's id. None where
    ``reader`` sees no such document. DocumentError ``no_work`` for a work there is not, FieldError for a
    work made of a title the database cannot hold or a country the region vocabulary does not (its IRI
    is named by it), DocumentNamed, or a refusal of ``guard_document``, and then nothing is changed."""
    async with connection.transaction():
        target = await target_of(connection, DOCUMENT, reader, document_id)
        if target is None:
            return None
        if isinstance(work, NewWork):
            if UNSTORABLE.search(work.title):
                raise FieldError("title", "not_storable")
            if not work.title.strip():  # the separators has_text trims, which the API's strip leaves
                raise FieldError("title", "required")
            if await unknown_regions(connection, [work.region]):
                raise FieldError("region", "not_offered")
        await guard_document(connection, document_id)
        await _unnamed(connection, document_id)
        if isinstance(work, ExistingWork):
            cursor = await connection.execute("SELECT id FROM work WHERE id = %s", (work.work_id,))
            if await cursor.fetchone() is None:
                raise DocumentError(f"no work {work.work_id}", code="no_work")
            work_id = work.work_id
        else:
            work_id = await new_entity(connection, "work")
            await connection.execute(
                "INSERT INTO work (id, title, region, short_title, owner_id) VALUES (%s, %s, %s, %s, %s)",
                (work_id, work.title, work.region, work.short_title, reader.account_id),
            )
        await connection.execute(
            "UPDATE document SET work_id = %s, updated_at = now() WHERE id = %s", (work_id, document_id)
        )
        return work_id


async def set_metadata(
    connection: psycopg.AsyncConnection, reader: Reader, document_id: UUID, given: Mapping[str, object]
) -> bool | None:
    """Set the metadata ``given`` (``METADATA``'s keys; a blank text, or None, none) - whether any
    changed; None where ``reader`` sees no such document. FieldError, DocumentNamed for the issuer or
    edition of a named document, or a refusal of ``guard``, and then nothing is changed."""
    async with connection.transaction():
        target = await target_of(connection, DOCUMENT, reader, document_id)
        if target is None:
            return None
        values = {key: _text(key, value) for key, value in given.items()}
        await guard(connection, document_id)
        cursor = await connection.execute(
            "SELECT title, issuer, edition, iri IS NOT NULL FROM document WHERE id = %s", (document_id,)
        )
        found = await cursor.fetchone()
        assert found is not None  # noqa: S101 - the tree's lock holds the document, which target_of found
        current = dict(zip(("title", "issuer", "edition"), found[:3], strict=True))
        changed = {key: value for key, value in values.items() if value != current[key]}
        if not changed:
            return False
        if found[3] and _NAMING & changed.keys():
            raise DocumentNamed(f"the document {document_id} is named by its IRI: its {sorted(changed)} stay")
        columns = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(key)) for key in changed)
        await connection.execute(
            sql.SQL("UPDATE document SET {}, updated_at = now() WHERE id = %s").format(columns),
            (*changed.values(), document_id),
        )
        await mark_edited(connection, document_id)
        return True


async def _unnamed(connection: psycopg.AsyncConnection, document_id: UUID) -> None:
    cursor = await connection.execute("SELECT iri FROM document WHERE id = %s", (document_id,))
    found = await cursor.fetchone()
    if found is not None and found[0] is not None:
        raise DocumentNamed(f"the document {document_id} is named by its IRI {found[0]}: its work stays")


def _text(key: str, value: object) -> str | None:
    most = METADATA.get(key)
    if most is None:
        raise FieldError(key, "unknown")
    if value is not None and not isinstance(value, str):
        raise FieldError(key, "not_text")
    if value is None or not value.strip():
        return None
    if UNSTORABLE.search(value):
        raise FieldError(key, "not_storable")
    if len(value) > most:
        raise FieldError(key, "too_long")
    return value
