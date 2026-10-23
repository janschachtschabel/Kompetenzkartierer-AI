"""The domain imports no framework and none of the layers built on it (Gesamtplan §6.5, plan M1 4.5)."""

import ast
import sys
from pathlib import Path

import app.domain

DOMAIN = Path(app.domain.__file__).parent
# what the rules need beyond the standard library: the lexicon's patterns, searched with a time limit
ALLOWED = frozenset({"regex"})


def outside_imports(source: str) -> list[str]:
    """The modules ``source`` imports that are neither the standard library, ALLOWED, nor the domain."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            names.append(node.module)
    return [name for name in names if not _allowed(name)]


def _allowed(name: str) -> bool:
    top = name.split(".")[0]
    within = name == "app.domain" or name.startswith("app.domain.")
    return top in sys.stdlib_module_names or top in ALLOWED or within


def test_the_check_finds_a_layer_and_a_framework_but_not_the_standard_library() -> None:
    lines = ["import hashlib", "import psycopg", "from app.db import pool", "from app.domain import l1"]
    source = "\n".join([*lines, "import regex"])

    assert outside_imports(source) == ["psycopg", "app.db"]


def test_the_domain_imports_the_standard_library_regex_and_itself_alone() -> None:
    modules = sorted(DOMAIN.rglob("*.py"))

    outside = {path.name: outside_imports(path.read_text(encoding="utf-8")) for path in modules}

    assert modules
    assert {name: found for name, found in outside.items() if found} == {}
