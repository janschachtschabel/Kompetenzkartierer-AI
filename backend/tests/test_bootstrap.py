"""``python -m app.bootstrap NAME``: the first admin and its token, once."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from app.core.tokens import looks_like_token, token_hash
from app.db.accounts import principal_for
from app.db.migrate import migrate
from tests.support import FAKE_PEPPER, without_settings_variables

pytestmark = pytest.mark.pg

BACKEND = Path(__file__).resolve().parents[1]


def bootstrap(
    database_url: str, name: str, pepper: str | None = FAKE_PEPPER
) -> subprocess.CompletedProcess[str]:
    with without_settings_variables():
        environment = {**os.environ, "DATABASE_URL": database_url}
    if pepper is not None:
        environment["API_KEY_PEPPER"] = pepper
    return subprocess.run(  # noqa: S603 - this interpreter and a fixed module
        [sys.executable, "-m", "app.bootstrap", name],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


async def principal_of(url: str, token: str) -> object:
    async with await psycopg.AsyncConnection.connect(url) as connection:
        return await principal_for(connection, token_hash(token, FAKE_PEPPER))


def test_the_first_admin_gets_a_token_once(database_url: str) -> None:
    migrate(database_url)

    first = bootstrap(database_url, "Erste Admin")
    second = bootstrap(database_url, "Zweite Admin")

    assert first.returncode == 0, first.stderr
    token = first.stdout.strip()
    assert looks_like_token(token)
    principal = asyncio.run(principal_of(database_url, token), loop_factory=asyncio.SelectorEventLoop)
    assert getattr(principal, "roles", None) == frozenset({"admin"})
    assert token not in first.stderr
    assert (second.returncode, second.stdout) == (2, "")
    assert "an admin exists" in second.stderr


def test_without_a_pepper_no_admin_is_made(database_url: str) -> None:
    migrate(database_url)

    refused = bootstrap(database_url, "Admin", pepper=None)

    assert (refused.returncode, refused.stdout) == (1, "")
    assert "API_KEY_PEPPER" in refused.stderr


def test_the_bootstrap_audits_the_account_and_its_key(database_url: str) -> None:
    migrate(database_url)

    assert bootstrap(database_url, "Erste Admin").returncode == 0

    with psycopg.connect(database_url) as connection:
        actions = [action for (action,) in connection.execute("SELECT action FROM audit_log ORDER BY id")]
    assert actions == ["account.create", "key.issue"]


def test_a_second_bootstrap_says_it_is_done_with_its_own_exit_code(database_url: str) -> None:
    migrate(database_url)
    bootstrap(database_url, "Erste Admin")

    assert bootstrap(database_url, "Zweite Admin").returncode == 2


def test_the_bootstrap_name_is_kept_in_one_spelling(database_url: str) -> None:
    # as the API keeps it: NFC, so the unique index sees one name however it was typed
    migrate(database_url)

    assert bootstrap(database_url, "Ju" + chr(0x308) + "rgen").returncode == 0

    with psycopg.connect(database_url) as connection:
        names = [name for (name,) in connection.execute("SELECT name FROM account")]
    assert names == ["J" + chr(0xFC) + "rgen"]


def test_a_bootstrap_name_with_a_hidden_sign_is_refused(database_url: str) -> None:
    migrate(database_url)

    refused = bootstrap(database_url, "Ad" + chr(0x200B) + "min")

    assert (refused.returncode, refused.stdout) == (1, "")
