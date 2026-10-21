"""Internal paths answer on the internal port only; on the public one they do not exist."""

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.internal import INTERNAL_PATHS
from app.api.paths import route_path
from tests.support import make_settings

PUBLIC = "http://testserver:8000"
INTERNAL = "http://testserver:9000"


@pytest.fixture
def app_client() -> TestClient:
    return TestClient(create_app(make_settings()), base_url=PUBLIC)


def test_health_answers_on_the_internal_port() -> None:
    client = TestClient(create_app(make_settings()), base_url=INTERNAL)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", sorted(INTERNAL_PATHS))
@pytest.mark.parametrize("suffix", ["", "/", "//"])
def test_an_internal_path_does_not_exist_on_the_public_port(
    app_client: TestClient, path: str, suffix: str
) -> None:
    response = app_client.get(path + suffix, follow_redirects=False)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_under_a_root_path_the_internal_path_stays_internal() -> None:
    # uvicorn puts the root path in front of the path; the router takes it off again
    client = TestClient(create_app(make_settings()), base_url=PUBLIC, root_path="/kka")

    response = client.get("/kka/health")

    assert response.status_code == 404


def test_under_a_root_path_health_answers_on_the_internal_port() -> None:
    client = TestClient(create_app(make_settings()), base_url=INTERNAL, root_path="/kka")

    assert client.get("/kka/health").status_code == 200


def test_internal_paths_are_not_in_the_openapi_spec(app_client: TestClient) -> None:
    paths = app_client.get("/openapi.json").json()["paths"]

    assert not set(paths) & INTERNAL_PATHS


def test_the_internal_port_follows_the_settings() -> None:
    client = TestClient(create_app(make_settings(internal_port=9100)), base_url="http://testserver:9100")

    assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    ("path", "root", "expected"),
    [
        ("/health", "", "/health"),
        ("/kka/health", "/kka", "/health"),
        ("/kka", "/kka", "/"),
        # only before a slash, as Starlette's router strips it
        ("/kkahealth", "/kka", "/kkahealth"),
        ("/other/health", "/kka", "/other/health"),
    ],
)
def test_route_path_strips_the_root_path_as_the_router_does(path: str, root: str, expected: str) -> None:
    assert route_path({"type": "http", "path": path, "root_path": root}) == expected
