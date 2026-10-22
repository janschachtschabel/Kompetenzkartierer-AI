"""What deploy/docker-compose.yml promises, read off the file.

The run itself (all services up, the migration exactly once, /ready 200) is the package's
check; these keep the safety properties from slipping out of the file afterwards.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
COMPOSE: dict[str, Any] = yaml.safe_load(TEXT)
SERVICES: dict[str, Any] = COMPOSE["services"]
APP = ["bucket", "migrate", "vocab", "api", "worker"]


def test_no_variable_of_the_developers_environment_is_read() -> None:
    # an interpolated ${OPENAI_API_KEY} would hand a real key to a container, and render it
    # into `docker compose config`
    assert not re.search(r"\$\{?[A-Za-z_]", TEXT)


def test_only_the_web_server_is_published_and_only_on_loopback() -> None:
    published = {name: service["ports"] for name, service in SERVICES.items() if service.get("ports")}

    assert published == {"web": ["127.0.0.1:18080:8080"]}


@pytest.mark.parametrize("name", [*APP, "web"])
def test_a_service_of_ours_runs_without_privileges_on_a_read_only_root(name: str) -> None:
    service = SERVICES[name]

    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]


@pytest.mark.parametrize("name", APP)
def test_secrets_come_as_files_not_as_values(name: str) -> None:
    environment = SERVICES[name]["environment"]
    secret_names = {"DATABASE_URL", "API_KEY_PEPPER", "S3_ACCESS_KEY", "S3_SECRET_KEY", "OPENAI_API_KEY"}

    assert not secret_names & set(environment)
    assert environment["DATABASE_URL_FILE"].startswith("/run/secrets/")


def test_every_third_party_image_is_pinned_by_digest() -> None:
    images = [service["image"] for service in SERVICES.values() if "build" not in service]
    third_party = [image for image in images if not image.startswith("kka-")]

    assert third_party
    assert all(re.search(r"@sha256:[0-9a-f]{64}$", image) for image in third_party), third_party


def test_the_migration_runs_once_and_before_api_and_worker() -> None:
    for name in ("api", "worker"):
        assert SERVICES[name]["depends_on"]["migrate"] == {"condition": "service_completed_successfully"}
    assert SERVICES["migrate"]["command"] == ["python", "-m", "app.db.migrate"]
    assert "replicas" not in SERVICES["migrate"].get("deploy", {})


def test_api_and_worker_run_twice() -> None:
    assert SERVICES["api"]["deploy"]["replicas"] == 2
    assert SERVICES["worker"]["deploy"]["replicas"] == 2


def test_the_secret_files_are_kept_out_of_git() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "/deploy/secrets/" in ignored
