"""Every request is named by X-Request-ID and written once to the log, without query values."""

import io
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.core.logging import configure_logging
from tests.support import make_settings

PUBLIC = "http://testserver:8000"
INTERNAL = "http://testserver:9000"
REQUEST_LOGGER = "app.api.request_log"


@pytest.fixture
def log(restore_logging: None) -> io.StringIO:
    stream = io.StringIO()
    configure_logging("INFO", "json", stream=stream)
    return stream


@pytest.fixture
def app() -> FastAPI:
    application = create_app(make_settings())

    async def boom() -> None:
        raise RuntimeError("database gone")

    application.add_api_route("/api/v1/boom", boom, tags=["system"])
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=PUBLIC) as test_client:
        yield test_client


def request_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    return [line for line in lines if line["logger"] == REQUEST_LOGGER]


def test_an_answer_carries_a_new_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/info")

    assert re.fullmatch(r"[0-9a-f]{12}", response.headers["X-Request-ID"])


def test_the_callers_request_id_is_kept_cleaned(client: TestClient) -> None:
    response = client.get("/api/v1/info", headers={"X-Request-ID": "abc-123 |x"})

    assert response.headers["X-Request-ID"] == "abc-123x"


def test_a_refused_internal_path_carries_a_request_id_too(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 404
    assert response.headers["X-Request-ID"]


def test_one_line_per_request_with_its_route_and_without_query_values(
    client: TestClient, log: io.StringIO
) -> None:
    response = client.get("/api/v1/info?q=Klimawandel&token=s3cret", headers={"x-client-trace-id": "t-1"})

    [line] = request_lines(log)
    assert line["method"] == "GET"
    assert line["path"] == "/api/v1/info?q&token"
    assert line["route"] == "/api/v1/info"
    assert line["status"] == 200
    assert isinstance(line["duration_ms"], int)
    assert line["request_id"] == response.headers["X-Request-ID"]
    assert line["trace_id"] == "t-1"
    assert "Klimawandel" not in log.getvalue()
    assert "s3cret" not in log.getvalue()


def test_the_line_names_no_client_address(client: TestClient, log: io.StringIO) -> None:
    client.get("/api/v1/info")

    [line] = request_lines(log)
    assert "client" not in line
    assert "testclient" not in log.getvalue()


def test_a_path_no_route_takes_is_logged_as_unmatched(client: TestClient, log: io.StringIO) -> None:
    client.get("/api/v1/nowhere")

    [line] = request_lines(log)
    assert line["status"] == 404
    assert line["route"] == "unmatched"


def test_the_openapi_route_is_named_by_its_template(client: TestClient, log: io.StringIO) -> None:
    client.get("/openapi.json")

    [line] = request_lines(log)
    assert line["route"] == "/openapi.json"


def test_a_control_sign_in_the_path_cannot_forge_a_line(client: TestClient, log: io.StringIO) -> None:
    client.get("/api/v1/x%0A%1B[31mforged")

    [line] = request_lines(log)
    assert "\n" not in line["path"]
    assert "\x1b" not in line["path"]


def test_an_answering_probe_writes_no_line(app: FastAPI, log: io.StringIO) -> None:
    with TestClient(app, base_url=INTERNAL) as internal:
        assert internal.get("/health").status_code == 200

    assert request_lines(log) == []


def test_an_unhandled_error_is_answered_500_and_logged_once(client: TestClient, log: io.StringIO) -> None:
    response = client.get("/api/v1/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "database gone" not in response.text
    lines = [json.loads(line) for line in log.getvalue().splitlines()]
    errors = [line for line in lines if line["level"] == "ERROR"]
    assert len(errors) == 1
    assert "RuntimeError: database gone" in errors[0]["exc"]
    [request] = request_lines(log)[-1:]
    assert request["status"] == 500
