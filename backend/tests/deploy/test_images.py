"""What the images promise the operators (T6), read off their build files.

The build itself runs in CI and in the Compose check; these keep the promises from slipping
out of the files in between: bases pinned, no root, a health check that really asks, no data
or secrets in the build context.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
API = (ROOT / "deploy" / "api.Dockerfile").read_text(encoding="utf-8")
WEB = (ROOT / "deploy" / "web.Dockerfile").read_text(encoding="utf-8")
NGINX = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")
IGNORED = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()


def _final_stage(dockerfile: str) -> str:
    return re.split(r"(?m)^FROM ", dockerfile)[-1]


@pytest.mark.parametrize("dockerfile", [API, WEB], ids=["api", "web"])
def test_every_base_is_pinned_by_digest(dockerfile: str) -> None:
    bases = re.findall(r"(?m)^FROM (\S+)", dockerfile)

    assert bases
    assert all(re.search(r"@sha256:[0-9a-f]{64}$", base) for base in bases), bases


def test_the_api_runs_as_user_10001() -> None:
    assert re.search(r"(?m)^USER 10001$", _final_stage(API))


def test_the_api_listens_beyond_the_container_on_both_ports() -> None:
    final = _final_stage(API)

    assert re.search(r"HOST=0\.0\.0\.0", final)
    assert re.search(r"(?m)^EXPOSE 8000 9000$", final)


def test_the_api_health_check_sends_a_get_to_the_internal_port() -> None:
    # wget --spider sends HEAD, which /health answers with 405: the container would never be healthy
    check = re.search(r"(?ms)^HEALTHCHECK .*?(?=^\S)", _final_stage(API) + "\nEND")

    assert check is not None
    assert "urlopen" in check.group(0) and "/health" in check.group(0)
    assert "INTERNAL_PORT" in check.group(0)
    assert "--spider" not in check.group(0)


def test_the_api_installs_only_hashed_wheels_from_the_lock_export() -> None:
    assert "requirements-api.txt" in API
    assert "--require-hashes" in API
    assert "--only-binary=:all:" in API


def test_the_api_carries_code_and_ontology_but_no_tests_or_data() -> None:
    copies = re.findall(r"(?m)^COPY (?:--\S+ )*(\S+)", _final_stage(API))

    assert "backend/app" in copies
    assert "ontology" in copies
    assert not [source for source in copies if re.search(r"tests|data|docs|\.env", source)]


def test_the_web_image_serves_the_built_spa_as_its_unprivileged_user() -> None:
    final = _final_stage(WEB)

    assert "frontend/dist" in final
    assert not re.search(r"(?m)^USER (root|0)$", final)
    assert "nginx.conf" in final


def test_nginx_falls_back_to_the_spa_and_hands_the_api_on() -> None:
    assert re.search(r"try_files \$uri \$uri/ /index\.html;", NGINX)
    assert re.search(r"location /api/ \{[^}]*proxy_pass http://api:8000;", NGINX)


@pytest.mark.parametrize(
    "header",
    ["X-Content-Type-Options", "Content-Security-Policy", "Referrer-Policy", "X-Frame-Options"],
)
def test_nginx_sends_the_security_headers_on_every_answer(header: str) -> None:
    # set once for the server and never again below: a location with an add_header of its own
    # would silently drop all of the server's
    directives = [line.strip() for line in NGINX.splitlines() if not line.strip().startswith("#")]
    assert re.search(rf"add_header {header} .+ always;", NGINX)
    in_server = [line for line in NGINX.splitlines() if re.match(r"    add_header ", line)]
    assert len([line for line in directives if line.startswith("add_header")]) == len(in_server)


def test_nginx_names_no_version() -> None:
    assert "server_tokens off;" in NGINX


@pytest.mark.parametrize(
    "pattern",
    [
        ".git",
        "**/.venv",
        "**/node_modules",
        "**/__pycache__",
        "backend/tests",
        "**/.env*",
        "data",
        ".worktrees",
    ],
)
def test_the_build_context_leaves_out(pattern: str) -> None:
    assert pattern in IGNORED
