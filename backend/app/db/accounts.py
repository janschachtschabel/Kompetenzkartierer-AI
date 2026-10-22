"""Accounts, roles, API keys, failed sign-ins and the audit log in the database.

Every function runs single statements on a connection the caller holds; a caller that needs
several to hold together (creating an account with its roles) runs them in its transaction.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from app.core.auth import Principal
from app.core.ids import new_id
from app.core.tokens import new_token, token_hash


class AccountExists(Exception):
    """An account of this name exists already (names compare without case)."""


async def create_account(connection: psycopg.AsyncConnection, name: str, roles: Iterable[str]) -> UUID:
    account_id = new_id()
    async with connection.transaction():
        try:
            await connection.execute("INSERT INTO account (id, name) VALUES (%s, %s)", (account_id, name))
        except psycopg.errors.UniqueViolation:
            raise AccountExists(name) from None
        for role in sorted(set(roles)):
            await connection.execute(
                "INSERT INTO role_grant (account_id, role) VALUES (%s, %s)", (account_id, role)
            )
    return account_id


async def issue_key(
    connection: psycopg.AsyncConnection, account_id: UUID, label: str, pepper: str
) -> tuple[UUID, str]:
    """A new key for the account: its id and the token, which exists only in this answer."""
    key_id, token = new_id(), new_token()
    await connection.execute(
        "INSERT INTO api_key (id, account_id, key_hash, label) VALUES (%s, %s, %s, %s)",
        (key_id, account_id, token_hash(token, pepper), label),
    )
    return key_id, token


async def revoke_key(connection: psycopg.AsyncConnection, key_id: UUID) -> bool:
    cursor = await connection.execute(
        "UPDATE api_key SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL RETURNING id", (key_id,)
    )
    return await cursor.fetchone() is not None


async def set_disabled(connection: psycopg.AsyncConnection, account_id: UUID, disabled: bool) -> bool:
    cursor = await connection.execute(
        "UPDATE account SET disabled_at = CASE WHEN %s THEN coalesce(disabled_at, now()) END"
        " WHERE id = %s RETURNING id",
        (disabled, account_id),
    )
    return await cursor.fetchone() is not None


async def principal_for(connection: psycopg.AsyncConnection, key_hash: bytes) -> Principal | None:
    """The active account a key hash belongs to; its use is noted at most once a minute."""
    cursor = await connection.execute(
        """
        WITH found AS (
            SELECT api_key.id AS key_id, account.id, account.name
            FROM api_key JOIN account ON account.id = api_key.account_id
            WHERE api_key.key_hash = %s AND api_key.revoked_at IS NULL AND account.disabled_at IS NULL
        ), touched AS (
            UPDATE api_key SET last_used_at = now()
            WHERE id IN (SELECT key_id FROM found)
              AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute')
        )
        SELECT found.id, found.name, array_remove(array_agg(role_grant.role), NULL)
        FROM found LEFT JOIN role_grant ON role_grant.account_id = found.id
        GROUP BY found.id, found.name
        """,
        (key_hash,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return Principal(account_id=row[0], name=row[1], roles=frozenset(row[2]))


async def admin_exists(connection: psycopg.AsyncConnection) -> bool:
    cursor = await connection.execute("SELECT EXISTS (SELECT 1 FROM role_grant WHERE role = 'admin')")
    row = await cursor.fetchone()
    return bool(row and row[0])


async def record_failure(connection: psycopg.AsyncConnection, source: str) -> None:
    """Note a failed sign-in from ``source``; rows older than a day go with it."""
    await connection.execute("INSERT INTO auth_failure (source) VALUES (%s)", (source,))
    await connection.execute("DELETE FROM auth_failure WHERE at < now() - interval '1 day'")


async def recent_failures(connection: psycopg.AsyncConnection, source: str, window_s: float) -> int:
    cursor = await connection.execute(
        "SELECT count(*) FROM auth_failure WHERE source = %s AND at > now() - make_interval(secs => %s)",
        (source, window_s),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def record_audit(
    connection: psycopg.AsyncConnection,
    actor_id: UUID | None,
    actor_name: str,
    action: str,
    subject: str,
    details: dict[str, Any],
    request_id: str,
) -> None:
    await connection.execute(
        "INSERT INTO audit_log (actor_id, actor_name, action, subject, details, request_id)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (actor_id, actor_name, action, subject, Jsonb(details), request_id),
    )


@dataclass(frozen=True)
class AccountRecord:
    id: UUID
    name: str
    roles: list[str]
    disabled: bool


async def get_account(connection: psycopg.AsyncConnection, account_id: UUID) -> AccountRecord | None:
    cursor = await connection.execute(
        "SELECT account.id, account.name,"
        " array_remove(array_agg(role_grant.role ORDER BY role_grant.role), NULL),"
        " account.disabled_at IS NOT NULL"
        " FROM account LEFT JOIN role_grant ON role_grant.account_id = account.id"
        " WHERE account.id = %s GROUP BY account.id",
        (account_id,),
    )
    row = await cursor.fetchone()
    return AccountRecord(row[0], row[1], list(row[2]), row[3]) if row else None
