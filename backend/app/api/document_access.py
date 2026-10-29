"""Who reads a document through the API (plan M1 7a): its owner, and the editors and admins, who see
every document (app/db/documents.py, DOCUMENT_VISIBLE); to anyone else it is none - 404, the same
answer as to a document that does not exist."""

from uuid import UUID

import psycopg
from fastapi import HTTPException

from app.api.errors import Refusal
from app.api.source_content import EDITORS, content_row
from app.core.auth import Principal
from app.core.settings import Settings
from app.db.documents import Document, get_document
from app.db.source_queries import Reader


def reader(who: Principal) -> Reader:
    assert who.account_id is not None  # noqa: S101 - require_account refuses visitors
    return Reader(account_id=who.account_id, sees_all=bool(who.roles & EDITORS))


async def visible_document(
    connection: psycopg.AsyncConnection, who: Principal, document_id: UUID
) -> Document:
    """The document, if the caller may read it; else 404 ``no_document``."""
    document = await get_document(connection, reader(who), document_id)
    if document is None:
        raise Refusal(404, "no_document", "No such document.")
    return document


async def readable_content(
    connection: psycopg.AsyncConnection, who: Principal, settings: Settings, document: Document
) -> None:
    """The entry's content still the owner's to read, as when the document was made - its own,
    every entry while an editor, one of no account while THIRD_PARTY_MARKDOWN opens it."""
    try:
        await content_row(connection, who, settings, document.source_id)
    except HTTPException as hidden:  # an entry no longer the owner's to see at all: hidden as well
        if hidden.status_code != 404:
            raise
        raise Refusal(403, "file_hidden", "The content of this entry is no longer yours to read.") from None
