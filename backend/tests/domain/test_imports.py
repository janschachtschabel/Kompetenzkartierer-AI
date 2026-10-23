"""The domain imports no framework and none of the layers built on it (Gesamtplan §6.5, plan M1 4.5)."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import app.domain

DOMAIN = Path(app.domain.__file__).parent
BACKEND = DOMAIN.parents[1]
# what the rules need beyond the standard library: the lexicon's patterns, searched with a time limit
ALLOWED = frozenset({"regex"})
# names the check gives a module that imports by a call, which no reading of its imports resolves
DYNAMIC = "<a call that imports>"
# what a fresh interpreter holds beyond what it started with once it has imported every module
_LOADED = """
import importlib, json, sys
before = set(sys.modules)
for name in sys.argv[1:]:
    importlib.import_module(name)
print(json.dumps(sorted(set(sys.modules) - before)))
"""


def outside_imports(source: str, package: str = "app.domain") -> list[str]:
    """The modules ``source`` - a module of ``package`` - imports that are neither the standard
    library, ALLOWED, nor the domain; DYNAMIC for each call that imports."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.extend(_imported_from(node, package))
        elif isinstance(node, ast.Call) and _imports(node.func):
            names.append(DYNAMIC)
    return [name for name in names if not _allowed(name)]


def _imported_from(node: ast.ImportFrom, package: str) -> list[str]:
    """What ``from <module> import <names>`` imports: the module, or - where it names none, as
    ``from .. import db`` does - the modules it names."""
    base = (
        importlib.util.resolve_name("." * node.level + (node.module or ""), package)
        if node.level
        else node.module
    )
    assert base is not None
    return [base] if node.module is not None else [f"{base}.{alias.name}" for alias in node.names]


def _imports(func: ast.expr) -> bool:
    return (isinstance(func, ast.Name) and func.id == "__import__") or (
        isinstance(func, ast.Attribute) and func.attr == "import_module"
    )


def _allowed(name: str) -> bool:
    top = name.split(".")[0]
    within = name == "app.domain" or name.startswith("app.domain.")
    return name != DYNAMIC and (top in sys.stdlib_module_names or top in ALLOWED or within)


def _module(path: Path) -> str:
    parts = path.relative_to(BACKEND).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def test_the_check_finds_a_layer_and_a_framework_but_not_the_standard_library() -> None:
    lines = ["import hashlib", "import psycopg", "from app.db import pool", "from app.domain import l1"]
    source = "\n".join([*lines, "import regex"])

    assert outside_imports(source) == ["psycopg", "app.db"]


def test_the_check_resolves_a_relative_import_and_finds_a_call_that_imports() -> None:
    lines = [
        "from . import l1",
        "from .wording import text_hash",
        "from .. import db",
        "from ..api import app",
    ]
    calls = ["importlib.import_module('psycopg')", "__import__('fastapi')"]

    assert outside_imports("\n".join([*lines, *calls])) == ["app.db", "app.api", DYNAMIC, DYNAMIC]


def test_the_domain_imports_the_standard_library_regex_and_itself_alone() -> None:
    modules = sorted(DOMAIN.rglob("*.py"))

    outside = {
        path.relative_to(DOMAIN).as_posix(): outside_imports(
            path.read_text(encoding="utf-8"), _module(path.parent / "__init__.py")
        )
        for path in modules
    }

    assert modules
    assert {name: found for name, found in outside.items() if found} == {}


def test_a_fresh_interpreter_importing_the_domain_loads_nothing_beyond_it() -> None:
    # what the reading of the sources could miss: an import a module of the standard library makes
    names = [_module(path) for path in sorted(DOMAIN.rglob("*.py"))]

    done = subprocess.run(  # noqa: S603 - fixed code and the domain's own module names
        [sys.executable, "-c", _LOADED, *names], cwd=BACKEND, capture_output=True, text=True, check=True
    )

    loaded = json.loads(done.stdout)
    assert "app.domain" in loaded
    assert [name for name in loaded if not _allowed(name) and name != "app"] == []
