"""What the check job found at each address (migration 0010_url_check), and the register status it
gives the candidates there: the entries of no account with that address and no file yet."""

from dataclasses import dataclass

import psycopg

from app.sources.register import CheckOutcome, DetectedKind, RegisterStatus

# The candidates' addresses no check has found out about yet; one a server asked to wait (429)
# is asked again
_UNCHECKED = """
    SELECT DISTINCT s.url FROM source s
    WHERE s.owner_id IS NULL AND s.url IS NOT NULL AND s.file_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM url_check c
            WHERE c.url_sha256 = sha256(convert_to(s.url, 'UTF8')) AND c.outcome <> 'throttled'
        )
    ORDER BY s.url
"""
_RECORD = """
    INSERT INTO url_check (url_sha256, url, outcome, status_code, final_url, content_type,
        detected_type, size_bytes, sha256, last_modified)
    VALUES (sha256(convert_to(%(url)s, 'UTF8')), %(url)s, %(outcome)s, %(status_code)s, %(final_url)s,
        %(content_type)s, %(detected_type)s, %(size)s, %(sha256)s, %(last_modified)s)
    ON CONFLICT (url_sha256) DO UPDATE SET outcome = EXCLUDED.outcome,
        status_code = EXCLUDED.status_code, final_url = EXCLUDED.final_url,
        content_type = EXCLUDED.content_type, detected_type = EXCLUDED.detected_type,
        size_bytes = EXCLUDED.size_bytes, sha256 = EXCLUDED.sha256,
        last_modified = EXCLUDED.last_modified, checked_at = now()
"""
_FOLLOW = """
    UPDATE source SET register_status = %(status)s, updated_at = now()
    WHERE owner_id IS NULL AND url = %(url)s AND file_id IS NULL AND register_status <> %(status)s
"""


@dataclass(frozen=True)
class UrlCheck:
    url: str
    outcome: CheckOutcome
    status_code: int | None = None
    final_url: str | None = None  # where the redirects ended, if any came
    content_type: str | None = None
    detected_type: DetectedKind | None = None
    size: int | None = None
    sha256: bytes | None = None
    last_modified: str | None = None


async def unchecked_addresses(connection: psycopg.AsyncConnection) -> list[str]:
    cursor = await connection.execute(_UNCHECKED)
    return [url for (url,) in await cursor.fetchall()]


async def record_check(
    connection: psycopg.AsyncConnection, check: UrlCheck, register_status: RegisterStatus | None
) -> None:
    """Keep what was found at the address (again, if a check found it before) and, unless
    ``register_status`` is none, give it to the candidates there - in one transaction."""
    async with connection.transaction():
        await connection.execute(
            _RECORD,
            {
                "url": check.url,
                "outcome": check.outcome,
                "status_code": check.status_code,
                "final_url": check.final_url,
                "content_type": check.content_type,
                "detected_type": check.detected_type,
                "size": check.size,
                "sha256": check.sha256,
                "last_modified": check.last_modified,
            },
        )
        if register_status is not None:
            await connection.execute(_FOLLOW, {"status": register_status, "url": check.url})
