"""What deploy/docker-compose.yml promises, read off the file.

The run itself (all services up, the migration exactly once, /ready 200) is the package's
check; these keep the safety properties from slipping out of the file afterwards.
"""

import ipaddress
import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from app.core.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
TEXT = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
COMPOSE: dict[str, Any] = yaml.safe_load(TEXT)
SERVICES: dict[str, Any] = COMPOSE["services"]
APP = ["bucket", "migrate", "vocab", "api", "worker"]
# The services that run on; the one-off steps end, and a restart would run them again
LASTING = ["postgres", "minio", "api", "worker", "web"]


def _seconds(duration: str) -> float:
    match = re.fullmatch(r"(\d+)(s|m)", duration)
    assert match, duration
    return int(match.group(1)) * (60 if match.group(2) == "m" else 1)


def test_no_variable_of_the_developers_environment_is_read() -> None:
    # an interpolated ${OPENAI_API_KEY} would hand a real key to a container, and render it
    # into `docker compose config`
    assert not re.search(r"\$\{?[A-Za-z_]", TEXT)


@pytest.mark.parametrize("name", SERVICES)
def test_no_variable_passes_through_from_the_shell_or_a_file(name: str) -> None:
    # "MISTRAL_API_KEY:" without a value takes the shell's, env_file a whole file's: neither
    # needs a $, and real keys are exported on the developers' machines
    service = SERVICES[name]

    assert "env_file" not in service
    environment = service.get("environment", {})
    assert isinstance(environment, dict), "a list may name a variable without its value"
    assert all(isinstance(value, str) and value for value in environment.values()), environment


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


def test_the_api_trusts_the_web_server_alone_to_name_the_client() -> None:
    # The network holds the gateway too: every connection to the published port comes from it,
    # and a host process could reach the API from there with an X-Forwarded-For of its choosing
    web = SERVICES["web"]["networks"]["default"]["ipv4_address"]
    network = COMPOSE["networks"]["default"]["ipam"]["config"][0]

    assert SERVICES["api"]["environment"]["FORWARDED_ALLOW_IPS"] == web
    # outside the range Docker hands out: no container started first can hold it
    assert ipaddress.ip_address(web) in ipaddress.ip_network(network["subnet"])
    assert ipaddress.ip_address(web) not in ipaddress.ip_network(network["ip_range"])


def test_the_database_counts_as_healthy_once_it_listens_on_tcp() -> None:
    # On the first start the entrypoint runs a server on its socket only, to make the database:
    # pg_isready over the socket says healthy then, and the migration finds port 5432 closed
    assert "-h 127.0.0.1" in " ".join(SERVICES["postgres"]["healthcheck"]["test"])


@pytest.mark.parametrize("name", LASTING)
def test_a_service_that_ends_with_an_error_is_started_again(name: str) -> None:
    # the worker ends with an error when its sweeper breaks, trusting a supervisor to restart it
    assert SERVICES[name]["restart"] == "unless-stopped"


def test_a_stopping_worker_may_finish_its_job_before_docker_kills_it() -> None:
    worker = SERVICES["worker"]
    default = Settings.model_fields["job_shutdown_grace_s"].default
    grace = float(worker["environment"].get("JOB_SHUTDOWN_GRACE_S", default))

    # Docker's default of 10 s would kill a busy worker; its job would wait for the lease to end
    assert _seconds(worker["stop_grace_period"]) >= grace + 5


def test_the_api_is_found_healthy_within_seconds_of_its_start() -> None:
    # the image checks every 30 s, and the web server waits for the first healthy check;
    # Compose keeps the image's test and only asks more often
    check = SERVICES["api"]["healthcheck"]

    assert "test" not in check
    assert _seconds(check["interval"]) <= 5


def test_the_secret_files_are_kept_out_of_git() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "/deploy/secrets/" in ignored
