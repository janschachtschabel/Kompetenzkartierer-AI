"""The OpenAPI spec names and describes the service, and every tag in it is declared and used."""

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


def test_info_names_the_service_and_its_version() -> None:
    client = TestClient(create_app(make_settings()), base_url="http://testserver:8000")

    response = client.get("/api/v1/info")

    assert response.status_code == 200
    assert response.json() == {"name": "Kompetenzkartierer-AI", "version": __version__}
