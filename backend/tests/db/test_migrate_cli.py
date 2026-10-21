"""``python -m app.db.migrate``: the packaged migrations, exit code 0 or 1, logs on stderr."""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from app.db.migrate import load_migrations
from tests.support import without_settings_variables

pytestmark = pytest.mark.pg

BACKEND = Path(__file__).resolve().parents[2]


def run_migrate(database_url: str) -> subprocess.CompletedProcess[str]:
    with without_settings_variables():
        environment = {**os.environ, "DATABASE_URL": database_url, "LOG_FORMAT": "json"}
    return subprocess.run(
        [sys.executable, "-m", "app.db.migrate"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_packaged_migrations_are_applied_once(database_url: str) -> None:
    first = run_migrate(database_url)
    second = run_migrate(database_url)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout == ""
    with psycopg.connect(database_url) as connection:
        count = connection.execute("SELECT count(*) FROM schema_migration").fetchone()
    assert count == (len(load_migrations()),)
    assert "0 migration(s) applied" in second.stderr


def test_a_refused_run_ends_with_1_and_names_no_password(database_url: str) -> None:
    assert run_migrate(database_url).returncode == 0
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO schema_migration (version, name, checksum) VALUES (999, '0999_future.sql', %s)",
            ("0" * 64,),
        )

    refused = run_migrate(database_url)

    assert refused.returncode == 1
    assert "newer" in refused.stderr
    password = conninfo_to_dict(database_url).get("password")
    assert password
    assert str(password) not in refused.stderr
