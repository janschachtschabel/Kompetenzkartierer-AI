"""The scanner's edges, each one PostgreSQL's lexer decides otherwise than a naive one."""

import re
from pathlib import Path

import pytest

from app.db.migrate import MigrationError, load_migrations


def load(tmp_path: Path, sql: str) -> list[str]:
    (tmp_path / "m").mkdir(exist_ok=True)
    (tmp_path / "m" / "0001_case.sql").write_text(sql, encoding="utf-8", newline="")
    return [migration.filename for migration in load_migrations(tmp_path / "m")]


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE FUNCTION f() RETURNS void LANGUAGE sql BEGIN ATOMIC END;\nCOMMIT;\nSELECT 1;",
        "SELECT 1; -- a note\rCOMMIT;\nSELECT 2;",
        "SELECT 1 AS ✓$a$;\nCOMMIT;\nSELECT 'x$a$';",
        "SELECT $✓$ it's $✓$;\nCOMMIT;\nSELECT 'y';",
        "SELECT 1 AS ✓e'x\\';\nCOMMIT;\nSELECT 'y';",
    ],
    ids=[
        "empty-atomic-body",
        "comment-ended-by-cr",
        "dollar-in-unicode-identifier",
        "unicode-dollar-tag",
        "e-after-unicode",
    ],
)
def test_a_commit_the_server_would_run_is_found(tmp_path: Path, sql: str) -> None:
    with pytest.raises(MigrationError, match=re.escape("0001_case.sql")):
        load(tmp_path, sql)


def test_block_comments_nest(tmp_path: Path) -> None:
    # without nesting the first */ would end the comment and COMMIT would be a statement
    assert load(tmp_path, "/* outer /* inner */ COMMIT; */\nSELECT 1;") == ["0001_case.sql"]
