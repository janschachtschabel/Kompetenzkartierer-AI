"""Finding transaction control in a migration file, by PostgreSQL's own quoting rules.

Comments (``--``, nested ``/* */``), strings (``'...'``, ``E'...'`` with backslash escapes),
quoted identifiers (``"..."``) and dollar-quoted bodies (``$tag$ ... $tag$``, a ``$`` inside an
identifier is none) are blanked out; what is left splits into statements at ``;``. A
statement that starts with BEGIN, COMMIT, ... controls the transaction - except inside a
function body written ``BEGIN ATOMIC ... END``.
"""

import re
from itertools import pairwise

CONTROL = frozenset({"begin", "commit", "rollback", "end", "start", "savepoint", "release", "abort"})
_DOLLAR_TAG = re.compile(r"\$(?:[^\W\d]\w*)?\$")


def transaction_control(sql: str) -> str | None:
    """The first statement of ``sql`` that controls the transaction, as its first words; else ``None``."""
    in_atomic_body = False
    for statement in visible(sql).split(";"):
        words = statement.lower().split()
        if not words:
            continue
        if in_atomic_body:
            in_atomic_body = words[0] != "end"
            continue
        if words[0] in CONTROL:
            return " ".join(words[:2])
        in_atomic_body = ("begin", "atomic") in pairwise(words)
    return None


def visible(sql: str) -> str:
    """``sql`` with comments, strings, quoted identifiers and dollar-quoted bodies blanked."""
    out: list[str] = []
    index, size = 0, len(sql)
    while index < size:
        start = index
        if sql.startswith("--", index):
            end = sql.find("\n", index)
            index = size if end < 0 else end
        elif sql.startswith("/*", index):
            index = _after_block_comment(sql, index)
        elif sql[index] in "eE" and sql.startswith("'", index + 1) and not _inside_word(sql, index):
            index = _after_quoted(sql, index + 2, "'", backslash=True)
        elif sql[index] in "'\"":
            index = _after_quoted(sql, index + 1, sql[index], backslash=False)
        elif sql[index] == "$" and not _inside_word(sql, index) and (tag := _DOLLAR_TAG.match(sql, index)):
            end = sql.find(tag.group(), tag.end())
            index = size if end < 0 else end + len(tag.group())
        else:
            out.append(sql[index])
            index += 1
            continue
        out.append(" " * (index - start))
    return "".join(out)


def _inside_word(sql: str, index: int) -> bool:
    return index > 0 and (sql[index - 1].isalnum() or sql[index - 1] in "_$")


def _after_block_comment(sql: str, index: int) -> int:
    depth, index = 1, index + 2
    while index < len(sql) and depth:
        if sql.startswith("/*", index):
            depth, index = depth + 1, index + 2
        elif sql.startswith("*/", index):
            depth, index = depth - 1, index + 2
        else:
            index += 1
    return index


def _after_quoted(sql: str, index: int, quote: str, *, backslash: bool) -> int:
    while index < len(sql):
        if backslash and sql[index] == "\\":
            index += 2
        elif sql[index] == quote:
            if sql.startswith(quote, index + 1):  # a doubled quote stands for itself
                index += 2
            else:
                return index + 1
        else:
            index += 1
    return index
