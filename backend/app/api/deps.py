"""Who may call an operation: FastAPI dependencies for routes.

``principal`` reads the bearer token; no header means a visitor (``ANONYMOUS``). A valid
token always passes: behind a proxy or a school's NAT many people share one address, and one
of them with a stale token must not lock out the rest. A header without a valid token is
refused (401) and counted against its source - an IPv4 address, or an IPv6 /64, which one
client holds whole; past AUTH_FAILURE_LIMIT failures within AUTH_FAILURE_WINDOW_S the source
gets 429 for its failures. With 256-bit tokens guessing is hopeless anyway; the limit keeps
garbage from costing a write per request. The source is the socket's peer unless it is one
of FORWARDED_ALLOW_IPS, whose X-Forwarded-For uvicorn reads instead. Routes then ask for what they need:
``require_account`` (writing, and always the language model: AI tokens are never free),
``require_role`` or ``public_read``, which lets visitors in as far as PUBLIC_ACCESS allows.
"""

import hashlib
import ipaddress
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import AsyncConnectionPool

from app.core.auth import ANONYMOUS, Principal
from app.core.settings import Settings
from app.core.tokens import looks_like_token, token_hash
from app.db.accounts import principal_for, recent_failures, record_failure

log = logging.getLogger(__name__)

UNKNOWN_SOURCE = "unknown"
_FAILURE_LOCK = 0x6B6B_6166  # "kkaf": the class of the per-source advisory locks
PublicLevel = Literal["lookup", "search"]
_OPENS = {"off": frozenset[str](), "lookup": frozenset({"lookup"}), "search": frozenset({"lookup", "search"})}


# Declares the scheme in the OpenAPI spec; the header itself is read below, where a malformed
# one is counted as a failure rather than taken for a visitor
_BEARER = HTTPBearer(auto_error=False, description="An API token an admin issued (kka_...)")


async def principal(
    request: Request, _declared: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER)]
) -> Principal:
    header = request.headers.get("authorization")
    if header is None:
        return ANONYMOUS
    settings: Settings = request.app.state.settings
    pool: AsyncConnectionPool = request.app.state.pool
    scheme, _, token = header.partition(" ")
    token = token.strip()
    async with pool.connection() as connection:
        found = None
        if scheme.lower() == "bearer" and looks_like_token(token):
            assert settings.api_key_pepper is not None  # noqa: S101 - create_app refuses to start without
            found = await principal_for(
                connection, token_hash(token, settings.api_key_pepper.get_secret_value())
            )
        if found is not None:
            return found
        source = failure_source(request.client.host if request.client else None)
        # one source at a time: parallel guesses would all read the count before any is written
        await connection.execute("SELECT pg_advisory_xact_lock(%s, hashtext(%s))", (_FAILURE_LOCK, source))
        failures = await recent_failures(connection, source, settings.auth_failure_window_s)
        if failures < settings.auth_failure_limit:
            await record_failure(connection, source)
            if failures + 1 == settings.auth_failure_limit:
                log.warning("sign-in failures reached the limit for source %s", _anonymous(source))
    # raised outside the block: an exception inside would roll the failure back
    if failures >= settings.auth_failure_limit:
        retry = str(int(settings.auth_failure_window_s))
        raise HTTPException(429, "Too many failed sign-ins; try again later.", headers={"Retry-After": retry})
    raise HTTPException(401, "The token is not valid.", headers={"WWW-Authenticate": "Bearer"})


def failure_source(host: str | None) -> str:
    """What the failure limit counts by: an IPv4 address, or the /64 an IPv6 address is in."""
    try:
        address = ipaddress.ip_address(host or "")
    except ValueError:
        return UNKNOWN_SOURCE
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is None:
        return str(ipaddress.IPv6Network(f"{address}/64", strict=False))
    return str(address.ipv4_mapped or address) if isinstance(address, ipaddress.IPv6Address) else str(address)


def _anonymous(source: str) -> str:
    """The source as a log line may hold it: an address is personal data."""
    return hashlib.sha256(source.encode()).hexdigest()[:12]


async def require_account(who: Annotated[Principal, Depends(principal)]) -> Principal:
    if who.anonymous:
        raise HTTPException(401, "A token is needed.", headers={"WWW-Authenticate": "Bearer"})
    return who


def require_role(*roles: str) -> Callable[..., Awaitable[Principal]]:
    """An account with one of ``roles``."""

    async def check(who: Annotated[Principal, Depends(require_account)]) -> Principal:
        if not who.roles & set(roles):
            raise HTTPException(403, "This needs another role.")
        return who

    return check


def public_read(level: PublicLevel) -> Callable[..., Awaitable[Principal]]:
    """Reading that visitors may do too, if PUBLIC_ACCESS opens ``level``."""

    async def check(request: Request, who: Annotated[Principal, Depends(principal)]) -> Principal:
        settings: Settings = request.app.state.settings
        if who.anonymous and level not in _OPENS[settings.public_access]:
            raise HTTPException(401, "A token is needed.", headers={"WWW-Authenticate": "Bearer"})
        return who

    return check
