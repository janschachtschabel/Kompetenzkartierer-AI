"""Who may call an operation: FastAPI dependencies for routes.

``principal`` reads the bearer token; no header means a visitor (``ANONYMOUS``), a header
without a valid token is refused and counted against its source. Past AUTH_FAILURE_LIMIT
failures in AUTH_FAILURE_WINDOW_S a source is refused before its token is looked at, a valid
one too - otherwise the limit would not stop guessing. Routes then ask for what they need:
``require_account`` (writing, and always the language model: AI tokens are never free),
``require_role`` or ``public_read``, which lets visitors in as far as PUBLIC_ACCESS allows.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request
from psycopg_pool import AsyncConnectionPool

from app.core.auth import ANONYMOUS, Principal
from app.core.settings import Settings
from app.core.tokens import looks_like_token, token_hash
from app.db.accounts import principal_for, recent_failures, record_failure

PublicLevel = Literal["lookup", "search"]
_OPENS = {"off": frozenset[str](), "lookup": frozenset({"lookup"}), "search": frozenset({"lookup", "search"})}


async def principal(request: Request) -> Principal:
    header = request.headers.get("authorization")
    if header is None:
        return ANONYMOUS
    settings: Settings = request.app.state.settings
    pool: AsyncConnectionPool = request.app.state.pool
    source = request.client.host if request.client else "unknown"
    scheme, _, token = header.partition(" ")
    token = token.strip()
    async with pool.connection() as connection:
        locked = await recent_failures(connection, source, settings.auth_failure_window_s)
        found = None
        if locked < settings.auth_failure_limit and scheme.lower() == "bearer" and looks_like_token(token):
            assert settings.api_key_pepper is not None  # noqa: S101 - create_app refuses to start without
            found = await principal_for(
                connection, token_hash(token, settings.api_key_pepper.get_secret_value())
            )
        if found is None and locked < settings.auth_failure_limit:
            await record_failure(connection, source)
    # raised outside the block: an exception inside would roll the failure back
    if locked >= settings.auth_failure_limit:
        retry = str(int(settings.auth_failure_window_s))
        raise HTTPException(429, "Too many failed sign-ins; try again later.", headers={"Retry-After": retry})
    if found is None:
        raise HTTPException(401, "The token is not valid.", headers={"WWW-Authenticate": "Bearer"})
    return found


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
