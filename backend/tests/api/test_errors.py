"""Every error the API answers has one shape: code, message, details (plan section 6.4)."""

import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from app.api.app import create_app
from app.api.errors import error_response
from tests.support import make_settings

PUBLIC = "http://testserver:8000"


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str


@pytest.fixture
def app() -> FastAPI:
    application = create_app(make_settings())

    async def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    async def locked() -> None:
        raise HTTPException(status_code=403, detail="This curriculum is not yours.")

    async def not_modified() -> None:
        raise HTTPException(status_code=304)

    async def no_content() -> None:
        raise HTTPException(status_code=204)

    async def closed() -> None:
        raise HTTPException(status_code=499, detail="The client went away.")

    async def conflict() -> None:
        raise HTTPException(status_code=409, detail={"field": "title"})

    async def create(draft: Draft) -> dict[str, str]:
        return {"title": draft.title}

    application.add_api_route("/api/v1/items/{item_id}", item, tags=["system"])
    application.add_api_route("/api/v1/locked", locked, tags=["system"])
    application.add_api_route("/api/v1/not-modified", not_modified, tags=["system"])
    application.add_api_route("/api/v1/no-content", no_content, tags=["system"])
    application.add_api_route("/api/v1/closed", closed, tags=["system"])
    application.add_api_route("/api/v1/conflict", conflict, tags=["system"])
    application.add_api_route("/api/v1/drafts", create, methods=["POST"], tags=["system"])
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=PUBLIC) as test_client:
        yield test_client


def test_an_unknown_path_answers_in_the_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/nowhere")

    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": "Not Found", "details": {}}


def test_a_wrong_method_answers_in_the_error_shape_and_names_the_allowed_ones(client: TestClient) -> None:
    response = client.delete("/api/v1/info")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET"


def test_an_http_exception_keeps_its_message(client: TestClient) -> None:
    response = client.get("/api/v1/locked")

    assert response.status_code == 403
    assert response.json() == {"code": "forbidden", "message": "This curriculum is not yours.", "details": {}}


def test_a_validation_error_names_the_field_but_never_the_input(client: TestClient) -> None:
    response = client.get("/api/v1/items/SECRET123x")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert body["message"]
    [error] = body["details"]["errors"]
    assert error["loc"] == ["path", "item_id"]
    assert error["type"]
    assert "SECRET123x" not in response.text


@pytest.mark.parametrize("path", ["/api/v1/not-modified", "/api/v1/no-content"])
def test_a_status_without_a_body_answers_without_one(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code in {204, 304}
    assert response.content == b""


def test_a_status_the_standard_does_not_name_keeps_its_number_and_message(client: TestClient) -> None:
    response = client.get("/api/v1/closed")

    assert response.status_code == 499
    assert response.json() == {"code": "http_499", "message": "The client went away.", "details": {}}


def test_a_mapping_detail_lands_in_the_details(client: TestClient) -> None:
    response = client.get("/api/v1/conflict")

    assert response.json() == {"code": "conflict", "message": "Conflict", "details": {"field": "title"}}


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "bad_request"),
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "not_found"),
        (405, "method_not_allowed"),
        (409, "conflict"),
        (413, "content_too_large"),
        (415, "unsupported_media_type"),
        (422, "unprocessable_content"),
        (429, "too_many_requests"),
        (500, "internal_server_error"),
        (503, "service_unavailable"),
    ],
)
def test_the_codes_are_fixed_whatever_the_python_version_calls_the_status(status: int, code: str) -> None:
    assert json.loads(bytes(error_response(status).body))["code"] == code


def test_an_unknown_key_in_a_body_is_not_echoed(client: TestClient) -> None:
    response = client.post("/api/v1/drafts", json={"title": "Optik", "sk-invented-key": 1})

    assert response.status_code == 422
    assert response.json()["details"]["errors"] == [{"loc": ["body", "_"], "type": "extra_forbidden"}]
    assert "sk-invented-key" not in response.text


def test_the_spec_documents_the_error_shape_for_validation_errors(app: FastAPI) -> None:
    spec = app.openapi()

    documented = spec["paths"]["/api/v1/items/{item_id}"]["get"]["responses"]["422"]
    assert documented["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorBody"}
    assert "HTTPValidationError" not in json.dumps(spec)
