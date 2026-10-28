"""The OpenAPI spec names and describes the service, and every tag in it is declared and used; the
editor's routes name the refusals they give."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.api.app import create_app
from tests.support import make_settings


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    client = TestClient(create_app(make_settings()), base_url="http://testserver:8000")
    response = client.get("/openapi.json")
    assert response.status_code == 200
    document: dict[str, Any] = response.json()
    return document


@pytest.mark.parametrize("field", ["title", "summary", "description"])
def test_the_spec_names_and_describes_the_service(spec: dict[str, Any], field: str) -> None:
    assert spec["info"][field].strip()


def test_the_spec_carries_the_package_version(spec: dict[str, Any]) -> None:
    assert spec["info"]["version"] == __version__


def test_every_declared_tag_is_described_and_used(spec: dict[str, Any]) -> None:
    operations = [operation for path in spec["paths"].values() for operation in path.values()]
    used = {tag for operation in operations for tag in operation["tags"]}
    declared = {tag["name"]: tag.get("description", "") for tag in spec["tags"]}

    assert declared, "no tags declared"
    assert set(declared) == used
    assert all(description.strip() for description in declared.values())


def test_every_operation_has_a_tag_and_a_summary(spec: dict[str, Any]) -> None:
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            assert operation.get("tags"), f"{method.upper()} {path} has no tag"
            assert operation.get("summary", "").strip(), f"{method.upper()} {path} has no summary"


def test_the_editor_s_routes_name_the_refusals_they_give(spec: dict[str, Any]) -> None:
    paths = spec["paths"]
    edited = paths["/api/v1/nodes/{node_id}"]["patch"]["responses"]
    reviewed = paths["/api/v1/documents/{document_id}/review"]["post"]["responses"]
    taken = [
        paths[path]["delete"]["responses"]
        for path in ("/api/v1/nodes/{node_id}", "/api/v1/statements/{statement_id}")
    ]

    assert "details.current" in edited["409"]["description"] and "no_form" in edited["409"]["description"]
    assert "invalid_field" in edited["422"]["description"]
    assert "details.stale" in reviewed["409"]["description"]
    for answers in (reviewed, *taken):
        assert "no_form" not in answers["409"]["description"]
        assert "invalid_field" not in answers.get("422", {}).get("description", "")


def test_info_names_the_service_its_version_and_what_visitors_may_do() -> None:
    # the start page asks it before anyone signs in: PUBLIC_ACCESS decides what it offers a visitor
    client = TestClient(create_app(make_settings()), base_url="http://testserver:8000")

    response = client.get("/api/v1/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Kompetenzkartierer-AI",
        "version": __version__,
        "public_access": "off",
        "max_upload_mb": 50,
    }


def test_info_names_the_upload_limit_so_the_page_checks_a_file_before_sending_it() -> None:
    client = TestClient(create_app(make_settings(max_upload_mb=12)), base_url="http://testserver:8000")

    assert client.get("/api/v1/info").json()["max_upload_mb"] == 12


def test_info_says_when_visitors_may_look_things_up() -> None:
    client = TestClient(create_app(make_settings(public_access="lookup")), base_url="http://testserver:8000")

    assert client.get("/api/v1/info").json()["public_access"] == "lookup"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_no_documentation_page_loads_assets_from_third_parties(path: str) -> None:
    # FastAPI's pages pull scripts, styles and fonts from CDNs into the visitor's browser
    client = TestClient(create_app(make_settings()), base_url="http://testserver:8000")

    assert client.get(path).status_code == 404
