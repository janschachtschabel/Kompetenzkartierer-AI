"""Which statements of a migration control the transaction: PostgreSQL's quoting, not a guess."""

import re
from pathlib import Path

import psycopg
import pytest

from app.db import migrate as runner
from app.db.migrate import MigrationError, load_migrations, migrate


def load(tmp_path: Path, sql: str) -> list[str]:
    (tmp_path / "m").mkdir(exist_ok=True)
    (tmp_path / "m" / "0001_case.sql").write_text(sql, encoding="utf-8")
    return [migration.filename for migration in load_migrations(tmp_path / "m")]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT E'it\\'s';\nCOMMIT;\nSELECT 'x';",
        "CREATE TABLE \"it's\" (id int);\nCOMMIT;\nSELECT 'x';",
        "SELECT 1 AS x$y$z;\nCOMMIT;\nSELECT 2 AS a$y$b;",
        'CREATE TABLE "a--" (id int);\nCOMMIT;',
        'CREATE TABLE "a/*" (id int);\nCOMMIT;\nSELECT 1; -- */',
    ],
    ids=[
        "escape-string",
        "quoted-identifier",
        "dollar-in-identifier",
        "dashes-in-identifier",
        "slash-star-in-identifier",
    ],
)
def test_a_commit_behind_tricky_quoting_is_still_found(tmp_path: Path, sql: str) -> None:
    with pytest.raises(MigrationError, match=re.escape("0001_case.sql")):
        load(tmp_path, sql)


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE FUNCTION f() RETURNS int LANGUAGE plpgsql AS $body1$\nBEGIN\n  RETURN 1;\nEND;\n$body1$;",
        "CREATE FUNCTION g() RETURNS int LANGUAGE sql\nBEGIN ATOMIC\n  SELECT 1;\n  SELECT 2;\nEND;",
        "/* outer /* inner COMMIT; */ still a comment COMMIT; */\nSELECT 1;",
        "COMMENT ON TABLE x IS 'COMMIT;';",
        "SELECT CASE WHEN true THEN 1 END;",
        'CREATE TABLE "begin" (id int);',
    ],
    ids=["tagged-body", "begin-atomic", "nested-comment", "commit-in-text", "case-end", "table-named-begin"],
)
def test_legitimate_sql_is_not_taken_for_transaction_control(tmp_path: Path, sql: str) -> None:
    assert load(tmp_path, sql) == ["0001_case.sql"]


@pytest.mark.pg
def test_a_file_that_ended_the_transaction_anyway_fails_loudly(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the last guard, should the scanner ever miss one: the runner checks its transaction is open
    monkeypatch.setattr(runner, "_transaction_control", lambda sql: None)
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "0001_slipped.sql").write_text("CREATE TABLE a (id int);\nCOMMIT;", encoding="utf-8")

    with pytest.raises(MigrationError, match="transaction"):
        migrate(database_url, tmp_path / "m")

    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT count(*) FROM schema_migration").fetchone() == (0,)
