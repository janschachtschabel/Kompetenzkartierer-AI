""".github/workflows/ci.yml runs every check of the repository, with pinned tools.

A green run needs a push; until then these keep the workflow from losing a check or taking an
action by a tag someone could move.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
WORKFLOW: dict[Any, Any] = yaml.safe_load(TEXT)
JOBS: dict[str, Any] = WORKFLOW["jobs"]
COMPOSE: dict[str, Any] = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))
PYPROJECT: dict[str, Any] = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
# PyYAML reads the key "on" as YAML 1.1 does: as True
TRIGGERS: dict[str, Any] = WORKFLOW["on"] if "on" in WORKFLOW else WORKFLOW[True]


def _commands() -> str:
    return "\n".join(str(step.get("run", "")) for job in JOBS.values() for step in job.get("steps", []))


def _smoke_test() -> str:
    steps = JOBS["images"]["steps"]
    return next(str(step["run"]) for step in steps if step.get("name") == "Smoke test of the whole service")


def _command(job: str, pattern: str) -> str:
    runs = [str(step.get("run", "")) for step in JOBS[job]["steps"]]
    return next(run for run in runs if re.search(pattern, run))


def test_every_action_is_pinned_by_its_commit() -> None:
    uses = re.findall(r"uses: (\S+)", TEXT)

    assert uses
    assert all(re.search(r"@[0-9a-f]{40}$", action) for action in uses), uses


def test_it_reads_the_repository_and_nothing_more() -> None:
    assert WORKFLOW["permissions"] == {"contents": "read"}
    # a job may widen them for itself
    assert all(job.get("permissions", {"contents": "read"}) == {"contents": "read"} for job in JOBS.values())


def test_no_later_step_can_read_the_checkout_s_token() -> None:
    steps = [step for job in JOBS.values() for step in job["steps"]]
    checkouts = [step for step in steps if "actions/checkout@" in step.get("uses", "")]

    assert checkouts
    assert all(step.get("with", {}).get("persist-credentials") is False for step in checkouts)


def test_a_branch_can_be_checked_by_hand_and_main_is_never_cut_short() -> None:
    # A green run on a test branch is the milestone's proof; a push alone starts nothing there
    assert "workflow_dispatch" in TRIGGERS
    assert "pull_request" in str(WORKFLOW["concurrency"]["cancel-in-progress"])


def test_every_job_and_every_request_has_a_deadline() -> None:
    assert all(job.get("timeout-minutes", 0) > 0 for job in JOBS.values())
    curls = re.findall(r"curl [^\n]*", _commands())
    assert curls
    assert all("--max-time" in curl for curl in curls), curls


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


def test_the_script_ci_runs_is_linted_and_typed_as_well() -> None:
    for tool in (r"ruff check", r"ruff format --check", r"mypy"):
        assert "make-secrets.py" in _command("backend", tool), tool


def test_the_tests_keep_their_coverage() -> None:
    floor = PYPROJECT["tool"]["coverage"]["report"]["fail_under"]

    assert "--cov=app" in _command("backend", r"-m pytest")
    assert floor >= 90


def test_the_database_and_object_store_tests_are_required_not_skipped() -> None:
    environment = JOBS["backend"]["env"]

    # GitHub sets CI=true, which turns a missing test service into a failure (tests/conftest.py)
    assert environment["KKA_TEST_DATABASE_URL"].startswith("postgresql://")
    assert environment["KKA_TEST_S3_URL"].startswith("http://127.0.0.1:")


def test_ci_tests_against_the_database_image_compose_runs() -> None:
    service = JOBS["backend"]["services"]["postgres"]

    assert service["image"] == COMPOSE["services"]["postgres"]["image"]
    # healthy once it listens on TCP, not while the first start's socket-only server runs
    assert "pg_isready -h 127.0.0.1" in service["options"]


def test_the_lock_is_installed_as_it_is() -> None:
    assert "uv sync --frozen" in _commands()


def test_the_smoke_test_starts_the_whole_service_and_asks_through_the_web_server() -> None:
    smoke = _smoke_test()

    assert "docker compose -f deploy/docker-compose.yml up" in smoke
    assert "127.0.0.1:18080/api/v1/info" in smoke


@pytest.mark.parametrize(
    ("what", "pattern"),
    [
        # no service waits for the vocabulary load: up -d stays green when it fails
        ("the vocabulary load ended well", r"compose -f deploy/docker-compose\.yml wait vocab"),
        ("both workers run", r"ps -q --status running worker \| wc -l\)\" = 2"),
        (
            "each API replica is ready",
            r"ready=\"[^\"]*:9000/ready'[\s\S]*"
            r"--index 1 api python -c \"\$ready\"\n.*--index 2 api python -c \"\$ready\"",
        ),
        # a trace id the client sends appears in the API's log line of the request
        (
            "the trace id reaches the log",
            r"x-client-trace-id: \$trace[\s\S]*logs api[^\n]*grep -\w*F \"\$trace\"",
        ),
    ],
)
def test_the_smoke_test_checks(what: str, pattern: str) -> None:
    assert re.search(pattern, _smoke_test()), what
