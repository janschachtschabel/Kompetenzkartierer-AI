"""What the images promise the operators (T6), read off their build files.

The build itself runs in CI and in the Compose check; these keep the promises from slipping
out of the files in between: bases pinned, no root, a health check that really asks, no data
or secrets in the build context.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

from app.api.security_headers import SECURITY_HEADERS
from app.vocab.loader import MODEL_DIRS

ROOT = Path(__file__).resolve().parents[3]
API = (ROOT / "deploy" / "api.Dockerfile").read_text(encoding="utf-8")
WEB = (ROOT / "deploy" / "web.Dockerfile").read_text(encoding="utf-8")
NGINX = (ROOT / "deploy" / "nginx.conf").read_text(encoding="utf-8")
# The API's part of the web server: none in the image, the proxy in Compose
API_OFF = (ROOT / "deploy" / "nginx-api-off.conf").read_text(encoding="utf-8")
API_PROXY = (ROOT / "deploy" / "nginx-api.conf").read_text(encoding="utf-8")
API_PART = "/etc/nginx/kka/api.conf"
COMPOSE: dict[str, Any] = yaml.safe_load((ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))
IGNORED = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
VITE = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")


def _final_stage(dockerfile: str) -> str:
    return re.split(r"(?m)^FROM ", dockerfile)[-1]


def _directives(config: str) -> list[str]:
    return [line.strip() for line in config.splitlines() if line.strip() and not line.strip().startswith("#")]


@pytest.mark.parametrize("dockerfile", [API, WEB], ids=["api", "web"])
def test_every_base_is_pinned_by_digest(dockerfile: str) -> None:
    bases = re.findall(r"(?m)^FROM (\S+)", dockerfile)

    assert bases
    assert all(re.search(r"@sha256:[0-9a-f]{64}$", base) for base in bases), bases


def test_the_api_runs_as_user_10001() -> None:
    # the last USER counts: a USER root after it would run the service as root
    assert re.findall(r"(?m)^USER (\S+)$", _final_stage(API))[-1] == "10001"


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


def test_the_api_carries_its_code_and_the_ontology_it_reads_nothing_else() -> None:
    # ontology/ also holds research notes and examples (3 MB); the service reads MODEL_DIRS
    copies = re.findall(r"(?m)^COPY (?:--\S+ )*(\S+)", _final_stage(API))
    ontology = sorted(source.removeprefix("ontology/") for source in copies if source.startswith("ontology"))

    assert "backend/app" in copies
    assert ontology == sorted(MODEL_DIRS)
    assert not [source for source in copies if re.search(r"tests|data|docs|\.env", source)]


def test_the_web_image_serves_the_built_spa_as_its_unprivileged_user() -> None:
    final = _final_stage(WEB)

    # the unprivileged build runs as 101; the plain nginx image would run as root
    assert re.match(r"nginxinc/nginx-unprivileged:\S+@sha256:", final)
    assert not re.search(r"(?m)^USER ", final)
    assert "frontend/dist" in final
    assert "nginx.conf" in final


def test_nginx_falls_back_to_the_spa() -> None:
    assert re.search(r"try_files \$uri \$uri/ /index\.html;", NGINX)


def test_the_image_names_no_api_host_and_answers_the_api_paths_with_404() -> None:
    # A host named in proxy_pass is resolved once, at start: nginx stops when it is missing (a
    # cluster's Service is rarely named "api"), and keeps the old address of a replica made anew
    assert "proxy_pass" not in NGINX
    assert f"include {API_PART};" in NGINX
    assert re.search(rf"(?m)^COPY deploy/nginx-api-off\.conf {re.escape(API_PART)}$", WEB)
    assert re.search(r"location /api/ \{\s*return 404;\s*\}", API_OFF)
    assert re.search(r"location = /openapi\.json \{\s*return 404;\s*\}", API_OFF)


def test_compose_puts_the_proxy_in_place_of_the_image_s_default() -> None:
    assert f"./nginx-api.conf:{API_PART}:ro" in COMPOSE["services"]["web"]["volumes"]


def test_compose_asks_docker_for_the_api_s_address_at_each_request() -> None:
    assert re.search(r"(?m)^resolver 127\.0\.0\.11 ", API_PROXY)
    assert "set $api http://api:8000;" in API_PROXY
    # every pass goes through the variable, a fixed host anywhere would be resolved at start again
    assert re.findall(r"proxy_pass (\S+);", API_PROXY) == ["$api", "$api"]
    assert "location /api/ {" in API_PROXY
    assert "location = /openapi.json {" in API_PROXY


def test_the_web_server_states_the_client_rather_than_appending_to_what_it_sent() -> None:
    # Appended, a client's own X-Forwarded-For would name its address: the API trusts this server
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in API_PROXY
    assert "$proxy_add_x_forwarded_for" not in API_PROXY


def test_the_proxy_headers_hold_for_both_api_locations() -> None:
    # set at the file's top level, the server's; a location with one of its own would drop them
    top_level = [line for line in API_PROXY.splitlines() if line.startswith("proxy_set_header ")]

    assert {line.split()[1] for line in top_level} == {"Host", "X-Forwarded-For", "X-Forwarded-Proto"}
    # with its port: FastAPI's redirect for a trailing slash builds its URL from Host ($host has none)
    assert "proxy_set_header Host $http_host;" in API_PROXY
    assert len([line for line in _directives(API_PROXY) if line.startswith("proxy_set_header")]) == 3


@pytest.mark.parametrize("header", SECURITY_HEADERS)
def test_the_api_s_security_headers_are_not_sent_twice(header: str) -> None:
    # the API sets them itself for a cluster; behind this server its own are sent, once
    assert f"proxy_hide_header {header};" in API_PROXY


@pytest.mark.parametrize(
    "header",
    ["X-Content-Type-Options", "Content-Security-Policy", "Referrer-Policy", "X-Frame-Options"],
)
def test_nginx_sends_the_security_headers_on_every_answer(header: str) -> None:
    # set once for the server and never again below: a location with an add_header of its own
    # would silently drop all of the server's
    assert re.search(rf"add_header {header} .+ always;", NGINX)
    in_server = [line for line in NGINX.splitlines() if re.match(r"    add_header ", line)]
    assert len([line for line in _directives(NGINX) if line.startswith("add_header")]) == len(in_server)
    assert not [line for line in _directives(API_OFF + API_PROXY) if line.startswith("add_header")]


def test_nginx_listens_on_ipv4_only() -> None:
    # A node booted without IPv6 refuses a [::] listener, and nginx would not start
    assert re.findall(r"(?m)^\s*listen (.+);", NGINX) == ["8080"]


def test_the_build_inlines_no_font_the_policy_would_block() -> None:
    # font-src 'self' blocks a data: font; Vite inlines assets below 4 KiB, a font subset among them
    assert "font-src 'self';" in NGINX
    assert re.search(r"assetsInlineLimit: 0\b", VITE)


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
        "deploy/secrets",
    ],
)
def test_the_build_context_leaves_out(pattern: str) -> None:
    assert pattern in IGNORED
