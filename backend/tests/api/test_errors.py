"""Every error the API answers has one shape: code, message, details (plan section 6.4)."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.support import make_settings

PUBLIC = "http://testserver:8000"


@pytest.fixture
def app() -> FastAPI:
    application = create_app(make_settings())

    async def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    async def locked() -> None:
        raise HTTPException(status_code=403, detail="This curriculum is not yours.")

    application.add_api_route("/api/v1/items/{item_id}", item, tags=["system"])
    application.add_api_route("/api/v1/locked", locked, tags=["system"])
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
