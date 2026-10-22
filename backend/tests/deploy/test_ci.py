""".github/workflows/ci.yml runs every check of the repository, with pinned tools.

A green run needs a push; until then these keep the workflow from losing a check or taking an
action by a tag someone could move.
"""

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
WORKFLOW: dict[str, Any] = yaml.safe_load(TEXT)
COMPOSE: dict[str, Any] = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))


def _commands() -> str:
    return "\n".join(
        str(step.get("run", "")) for job in WORKFLOW["jobs"].values() for step in job.get("steps", [])
    )


def test_every_action_is_pinned_by_its_commit() -> None:
    uses = re.findall(r"uses: (\S+)", TEXT)

    assert uses
    assert all(re.search(r"@[0-9a-f]{40}$", action) for action in uses), uses


def test_it_reads_the_repository_and_nothing_more() -> None:
    assert WORKFLOW["permissions"] == {"contents": "read"}


def test_every_check_of_the_repository_runs() -> None:
    commands = _commands()

    for check in [
        "pruefung/pruefe.py",
        "ruff check",
        "ruff format --check",
        "mypy",
        "pytest",
        "npm ci",
        "npm test",
        "npm run lint",
        "npm run build",
        "deploy/api.Dockerfile",
        "deploy/web.Dockerfile",
    ]:
        assert check in commands, check


def test_the_database_and_object_store_tests_are_required_not_skipped() -> None:
    environment = WORKFLOW["jobs"]["backend"]["env"]

    # GitHub sets CI=true, which turns a missing test service into a failure (tests/conftest.py)
    assert environment["KKA_TEST_DATABASE_URL"].startswith("postgresql://")
    assert environment["KKA_TEST_S3_URL"].startswith("http://127.0.0.1:")


def test_ci_tests_against_the_database_image_compose_runs() -> None:
    service = WORKFLOW["jobs"]["backend"]["services"]["postgres"]["image"]

    assert service == COMPOSE["services"]["postgres"]["image"]


def test_the_lock_is_installed_as_it_is() -> None:
    assert "uv sync --frozen" in _commands()


def test_the_smoke_test_starts_the_whole_service_and_asks_through_the_web_server() -> None:
    commands = _commands()

    assert "docker compose -f deploy/docker-compose.yml up" in commands
    assert "127.0.0.1:18080/api/v1/info" in commands
