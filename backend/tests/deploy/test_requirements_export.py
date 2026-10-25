"""The image installs deploy/requirements-api.txt, the export of uv.lock without the dev group.

The export is a file of its own because the image has no uv (pip installs it with
--require-hashes). A lock updated without a new export would build an image from other
versions than the tests ran with; this keeps the two equal.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / "backend" / "uv.lock"
EXPORT = ROOT / "deploy" / "requirements-api.txt"
PROJECT = "kompetenzkartierer-ai"


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_closure(lock: dict[str, Any]) -> dict[str, str]:
    """Name -> version of every package the project needs at runtime, extras followed."""
    packages = {_normal(p["name"]): p for p in lock["package"]}
    wanted: dict[str, str] = {}
    pending: list[tuple[str, tuple[str, ...]]] = [
        (_normal(dep["name"]), tuple(dep.get("extra", ()))) for dep in packages[PROJECT]["dependencies"]
    ]
    seen: set[tuple[str, tuple[str, ...]]] = set()
    while pending:
        name, extras = pending.pop()
        if (name, extras) in seen:
            continue
        seen.add((name, extras))
        package = packages[name]
        wanted[name] = package["version"]
        deps = list(package.get("dependencies", []))
        for extra in extras:
            deps += package.get("optional-dependencies", {}).get(extra, [])
        pending += [(_normal(dep["name"]), tuple(dep.get("extra", ()))) for dep in deps]
    return wanted


def exported(text: str) -> tuple[dict[str, str], list[str]]:
    """Name -> version of the export, and the names that came without a hash."""
    pinned: dict[str, str] = {}
    unhashed: list[str] = []
    for block in re.split(r"\n(?=[A-Za-z0-9])", text):
        head = block.split("\n", 1)[0]
        match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", head)
        if not match:
            continue
        name = _normal(match.group(1))
        pinned[name] = match.group(2)
        if "--hash=sha256:" not in block:
            unhashed.append(name)
    return pinned, unhashed


def test_the_export_pins_exactly_the_runtime_packages_of_the_lock() -> None:
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    pinned, _ = exported(EXPORT.read_text(encoding="utf-8"))

    assert pinned == runtime_closure(lock)


def test_every_exported_package_carries_its_hashes() -> None:
    _, unhashed = exported(EXPORT.read_text(encoding="utf-8"))

    assert unhashed == []


def test_the_dev_tools_stay_out_of_the_image() -> None:
    pinned, _ = exported(EXPORT.read_text(encoding="utf-8"))

    assert not {"pytest", "mypy", "ruff"} & pinned.keys()


def test_the_worker_s_shacl_gate_ships_in_the_image() -> None:
    # X5 validates each document against the Kern's shapes (plan M1 8.4)
    pinned, _ = exported(EXPORT.read_text(encoding="utf-8"))

    assert "pyshacl" in pinned


def test_the_reader_sees_a_package_without_a_hash() -> None:
    # the guard on the parser: a line without hashes must be told apart
    pinned, unhashed = exported("anyio==4.15.1 \\\n    --hash=sha256:ab\nidna==3.10\n")

    assert pinned == {"anyio": "4.15.1", "idna": "3.10"}
    assert unhashed == ["idna"]
