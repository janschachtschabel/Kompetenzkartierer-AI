"""Every request is named by X-Request-ID and written once to the log, without query values."""

import io
import json
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from starlette.background import BackgroundTask

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

    async def broken_stream() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"first chunk"
            raise RuntimeError("disk gone")

        return StreamingResponse(chunks(), media_type="text/plain")

    def paging(page: int = 1) -> int:
        return page

    async def search(q: str, page: int = Depends(paging)) -> dict[str, object]:
        return {"q": q, "page": page}

    async def failing_task() -> None:
        raise RuntimeError("mail server gone")

    async def queued() -> JSONResponse:
        return JSONResponse({"status": "queued"}, background=BackgroundTask(failing_task))

    application.add_api_route("/api/v1/search", search, tags=["system"])
    application.add_api_route("/api/v1/queued", queued, tags=["system"])
    application.add_api_route("/api/v1/boom", boom, tags=["system"])
    application.add_api_route("/api/v1/stream", broken_stream, tags=["system"])
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=PUBLIC) as test_client:
        yield test_client


def request_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    return [line for line in lines if line["logger"] == REQUEST_LOGGER and "status" in line]


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
    assert line["path"] == "/api/v1/info?_&_"
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
    assert body["code"] == "internal_server_error"
    assert body["details"] == {"request_id": response.headers["X-Request-ID"]}
    assert "database gone" not in response.text
    lines = [json.loads(line) for line in log.getvalue().splitlines()]
    errors = [line for line in lines if line["level"] == "ERROR"]
    assert len(errors) == 1
    assert "RuntimeError: database gone" in errors[0]["exc"]
    [request] = request_lines(log)
    assert request["status"] == 500


def test_only_query_names_the_route_declares_are_logged(client: TestClient, log: io.StringIO) -> None:
    # a padded base64 token and a search term written as a key look like names, but are values
    client.get("/api/v1/search?s3cretTokenValue&q=x&Klimawandel=&page=2&dGhpcyBpcyBhIHNlY3JldA==")

    [line] = request_lines(log)
    assert line["path"] == "/api/v1/search?_&q&_&page&_"
    for value in ("s3cretTokenValue", "Klimawandel", "dGhpcyBpcyBhIHNlY3JldA"):
        assert value not in log.getvalue()


def test_an_invented_method_is_logged_as_other(client: TestClient, log: io.StringIO) -> None:
    client.request("GET|forged|" + "X" * 2000, "/api/v1/info")

    [line] = request_lines(log)
    assert line["method"] == "other"
    assert "forged" not in log.getvalue().lower()


def test_an_error_after_the_answer_began_counts_as_a_failed_request(
    client: TestClient, log: io.StringIO
) -> None:
    labels = {"method": "GET", "route": "/api/v1/stream"}
    failed = REGISTRY.get_sample_value("kka_http_requests_total", {**labels, "status": "500"}) or 0.0

    client.get("/api/v1/stream")

    [line] = request_lines(log)
    assert line["status"] == 500
    assert line["aborted"] is True
    assert REGISTRY.get_sample_value("kka_http_requests_total", {**labels, "status": "500"}) == failed + 1


def test_an_error_after_a_complete_answer_keeps_its_status(client: TestClient, log: io.StringIO) -> None:
    # a background task fails after the client got its whole answer
    response = client.get("/api/v1/queued")

    assert response.json() == {"status": "queued"}
    [line] = request_lines(log)
    assert line["status"] == 200
    assert "aborted" not in line
    assert any(
        "mail server gone" in json.loads(entry).get("exc", "") for entry in log.getvalue().splitlines()
    )


def test_a_route_added_after_the_first_request_is_named(app: FastAPI, log: io.StringIO) -> None:
    with TestClient(app, base_url=PUBLIC) as client:
        client.get("/api/v1/info")

        async def late(item_id: int) -> dict[str, int]:
            return {"id": item_id}

        app.add_api_route("/api/v1/late/{item_id}", late, tags=["system"])
        client.get("/api/v1/late/7")

    assert [line["route"] for line in request_lines(log)] == ["/api/v1/info", "/api/v1/late/{item_id}"]
