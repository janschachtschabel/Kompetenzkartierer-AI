"""The migration runner's guards: no transaction control in files, bounded waits, clear failures."""

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from app.db import migrate as runner
from app.db.migrate import LOCK_KEY, MigrationError, load_migrations, migrate
from tests.support import lock_held, without_settings_variables

pytestmark = pytest.mark.pg

BACKEND = Path(__file__).resolve().parents[2]


def write(directory: Path, files: dict[str, str]) -> Path:
    directory.mkdir(exist_ok=True)
    for name, content in files.items():
        (directory / name).write_text(content, encoding="utf-8")
    return directory


@pytest.mark.parametrize(
    "statement",
    ["BEGIN;", "begin transaction;", "COMMIT;", "ROLLBACK;", "END;", "START TRANSACTION;", "SAVEPOINT a;"],
)
def test_a_file_with_its_own_transaction_control_is_refused(tmp_path: Path, statement: str) -> None:
    # it would commit the runner's transaction halfway and leave the file applied in part
    files = {"0001_own.sql": f"CREATE TABLE a (id int);\n{statement}\nCREATE TABLE b (id int);\n"}

    with pytest.raises(MigrationError, match=re.escape("0001_own.sql")):
        load_migrations(write(tmp_path / "m", files))


def test_begin_and_end_inside_a_function_body_are_no_transaction_control(tmp_path: Path) -> None:
    body = """\
CREATE FUNCTION touch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.changed_at := now();
    RETURN NEW;
END;
$$;
-- COMMIT; in a comment is no statement either
"""

    loaded = load_migrations(write(tmp_path / "m", {"0001_fn.sql": body}))

    assert [migration.filename for migration in loaded] == ["0001_fn.sql"]


def test_a_run_waiting_for_the_lock_says_so(
    database_url: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    directory = write(tmp_path / "m", {"0001_first.sql": "CREATE TABLE first (id int);"})
    with psycopg.connect(database_url, autocommit=True) as holder:
        holder.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        caplog.set_level(logging.INFO, logger="app.db.migrate")
        result: list[list[int]] = []
        thread = threading.Thread(target=lambda: result.append(migrate(database_url, directory)))
        thread.start()
        deadline = time.monotonic() + 10
        while "waiting for the migration lock" not in caplog.text and time.monotonic() < deadline:
            time.sleep(0.05)
        holder.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        thread.join(timeout=30)

    assert "waiting for the migration lock" in caplog.text
    assert result == [[1]]


def test_a_migration_blocked_by_a_table_lock_gives_up(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # waiting behind a long transaction, an ALTER would block all traffic on the table
    migrate(database_url, write(tmp_path / "m", {"0001_first.sql": "CREATE TABLE first (id int);"}))
    write(tmp_path / "m", {"0002_alter.sql": "ALTER TABLE first ADD COLUMN name text;"})
    monkeypatch.setattr(runner, "LOCK_TIMEOUT", "300ms")
    with (
        lock_held(database_url, "LOCK TABLE first IN ACCESS SHARE MODE", at_most_s=5),
        pytest.raises(MigrationError, match=re.escape("0002_alter.sql")),
    ):
        migrate(database_url, tmp_path / "m")


def run_migrate(database_url: str, log_format: str = "json") -> subprocess.CompletedProcess[str]:
    with without_settings_variables():
        environment = {**os.environ, "DATABASE_URL": database_url, "LOG_FORMAT": log_format}
    return subprocess.run(
        [sys.executable, "-m", "app.db.migrate"],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("log_format", ["json", "text"])
@pytest.mark.parametrize("target", ["wrong-password", "no-server"])
def test_a_database_the_command_cannot_reach_ends_in_one_log_line(
    database_url: str, target: str, log_format: str
) -> None:
    url = (
        make_conninfo(database_url, password="wrong-invented")  # noqa: S106 - an invented wrong one
        if target == "wrong-password"
        else "postgresql://kka:fake@127.0.0.1:1/kka"
    )

    refused = run_migrate(url, log_format)

    assert refused.returncode == 1
    lines = refused.stderr.splitlines()
    assert len(lines) == 1, refused.stderr
    message = json.loads(lines[0])["message"] if log_format == "json" else lines[0]
    assert "migration stopped" in message
    assert "wrong-invented" not in refused.stderr


SLEEPING = (
    "SELECT count(*) FROM pg_stat_activity"
    " WHERE query LIKE 'SELECT pg_sleep(30)%' AND pid <> pg_backend_pid()"
)


def test_a_connection_lost_mid_run_names_its_cause(database_url: str, tmp_path: Path) -> None:
    # releasing the lock on the dead connection must not hide why the run stopped
    directory = write(tmp_path / "m", {"0001_slow.sql": "SELECT pg_sleep(30);"})
    outcome: list[BaseException] = []

    def run() -> None:
        try:
            migrate(database_url, directory)
        except BaseException as error:  # reported below
            outcome.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    with psycopg.connect(database_url, autocommit=True) as admin:
        deadline = time.monotonic() + 10
        while not admin.execute(SLEEPING).fetchone()[0]:  # type: ignore[index]
            assert time.monotonic() < deadline, "the migration did not start"
            time.sleep(0.05)
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            " WHERE query LIKE 'SELECT pg_sleep(30)%' AND pid <> pg_backend_pid()"
        )
    thread.join(timeout=30)

    [error] = outcome
    assert isinstance(error, MigrationError)
    assert "0001_slow.sql failed" in str(error)
    assert "terminat" in str(error)
