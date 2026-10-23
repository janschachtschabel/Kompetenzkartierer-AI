"""Who may read the content of a register entry - its file, its conversion (plan M1, 1.10, 3.6).

Its owner and the editors. The content of an entry of no account (seed, research) goes, beside
them, to whom THIRD_PARTY_MARKDOWN names: ``hidden`` nobody, ``accounts`` every account,
``public`` visitors too - these only where PUBLIC_ACCESS lets them in at all: the stricter rule
holds. Another account's upload is the 404 of an entry that does not exist.
"""

from typing import Any
from uuid import UUID

import psycopg
from fastapi import HTTPException

from app.api.errors import Refusal
from app.core.auth import Principal
from app.core.settings import Settings
from app.db.source_queries import Reader, get_source, ownerless_source

EDITORS = frozenset({"redaktion", "admin"})


async def content_row(
    connection: psycopg.AsyncConnection, who: Principal, settings: Settings, source_id: UUID
) -> dict[str, Any]:
    """The entry, where ``who`` may read its content; 401, 404 or 403 ``file_hidden`` otherwise."""
    opened_to = settings.third_party_markdown
    if who.anonymous:
        to_visitors = opened_to == "public" and settings.public_access != "off"
        row = await ownerless_source(connection, source_id) if to_visitors else None
        if row is None:
            raise HTTPException(401, "A token is needed.", headers={"WWW-Authenticate": "Bearer"})
        return row
    assert who.account_id is not None  # noqa: S101 - a principal of no account is anonymous
    found = await get_source(connection, Reader(who.account_id, bool(who.roles & EDITORS)), source_id)
    if found is None:
        raise HTTPException(404, "No such register entry.")
    row = found[0]
    own = row["owner_id"] is not None and row["owner_id"] == who.account_id
    if not own and not who.roles & EDITORS and opened_to == "hidden":
        raise Refusal(403, "file_hidden", "The file of this entry is for its editors only.")
    return row
