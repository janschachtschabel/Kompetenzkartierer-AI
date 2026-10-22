"""``python -m app.bootstrap NAME``: the first admin account and its token.

Without an admin nobody could hand out tokens, so the operator makes the first one here. The
token goes to stdout, once - the only place it ever appears; logs go to stderr. Run it
interactively (``kubectl exec -it``, ``docker compose run``), not as a job whose output a log
system collects. When an admin who can sign in exists, the command refuses with exit code 2
(done already); further accounts come through the API. Any other failure is exit code 1.
"""

import asyncio
import logging
import sys

import psycopg

from app.core.auth import plain_text
from app.core.logging import configure_logging
from app.core.settings import Settings
from app.db import accounts as store
from app.db.pool import CONNECTION_OPTIONS

log = logging.getLogger("app.bootstrap")  # also when run as __main__

DONE_ALREADY = 2


async def make_first_admin(settings: Settings, name: str) -> str | None:
    """The new admin's token, or ``None`` if an admin exists."""
    assert settings.api_key_pepper is not None  # noqa: S101 - checked by main
    url = settings.database_url.get_secret_value()
    connection = await psycopg.AsyncConnection.connect(url, **CONNECTION_OPTIONS)
    async with connection, connection.transaction():
        # one bootstrap at a time: two operators at once would make two admins
        await connection.execute("LOCK TABLE role_grant IN SHARE ROW EXCLUSIVE MODE")
        if await store.admin_exists(connection):
            return None
        account = await store.create_account(connection, name, ["admin"])
        pepper = settings.api_key_pepper.get_secret_value()
        key, token = await store.issue_key(connection, account, "bootstrap", pepper)
        details = {"roles": ["admin"]}
        await store.record_audit(
            connection, None, "bootstrap", "account.create", f"account:{account}", details, ""
        )
        await store.record_audit(
            connection, None, "bootstrap", "key.issue", f"key:{key}", {"account": str(account)}, ""
        )
    return token


def main(arguments: list[str]) -> int:
    settings = Settings()
    configure_logging(settings.log_level, settings.log_format, stream=sys.stderr)
    if len(arguments) != 1 or not arguments[0].strip():
        log.error("usage: python -m app.bootstrap NAME")
        return 1
    if settings.api_key_pepper is None:
        log.error("API_KEY_PEPPER is not set: tokens are checked against it")
        return 1
    try:
        name = plain_text(arguments[0].strip())
    except ValueError as error:
        log.error("NAME %s", error)
        return 1
    try:
        token = asyncio.run(make_first_admin(settings, name), loop_factory=asyncio.SelectorEventLoop)
    except psycopg.Error as error:
        log.error("no admin made: %s", " ".join(str(error).split()))
        return 1
    if token is None:
        log.error("an admin exists already; further accounts come through the API")
        return DONE_ALREADY
    log.info("admin %s made; its token follows on stdout, once", name)
    print(token)  # the one place the token is shown
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
