"""The runner's last guard: a file that ended its transaction is reported, never recorded."""

from pathlib import Path

import psycopg
import pytest

from app.db import migrate as runner
from app.db.migrate import MigrationError, migrate

pytestmark = pytest.mark.pg


@pytest.fixture(autouse=True)
def scanner_misses_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    # as if the scanner had missed the statement: only the guard stands
    monkeypatch.setattr(runner, "_transaction_control", lambda sql: None)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE a (id int);\nCOMMIT AND CHAIN;\nCREATE TABLE b (id int);",
        "CREATE TABLE a (id int);\nCOMMIT;\nBEGIN;\nCREATE TABLE b (id int);",
        "CREATE TABLE a (id int);\nCOMMIT;\nSELECT 1 / 0;",
    ],
    ids=["commit-and-chain", "commit-then-begin", "fails-after-commit"],
)
def test_a_file_that_committed_part_of_itself_is_reported_and_not_recorded(
    database_url: str, tmp_path: Path, sql: str
) -> None:
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "0001_part.sql").write_text(sql, encoding="utf-8")

    with pytest.raises(MigrationError, match="ended the runner's transaction"):
        migrate(database_url, tmp_path / "m")

    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM schema_migration").fetchone() == (0,)
