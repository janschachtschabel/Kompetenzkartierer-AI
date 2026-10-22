"""Every answer of the API tells a browser not to sniff, frame or load anything from it.

In Compose the web server sets these headers; in a cluster the ingress hands /api/v1 straight
to the API, so it sets them itself - also on errors and on the answers its middlewares make.
"""

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.api.app import create_app
from tests.support import make_settings

PUBLIC = "http://testserver:8000"
INTERNAL = "http://testserver:9000"
EXPECTED = {
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


@pytest.fixture
def app() -> FastAPI:
    application = create_app(make_settings())

    async def broken() -> None:
        raise RuntimeError("invented failure")

    async def own_policy(response: Response) -> dict[str, str]:
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return {}

    application.add_api_route("/api/v1/broken", broken)
    application.add_api_route("/api/v1/own-policy", own_policy)
    return application


@pytest.mark.parametrize(
    ("base", "path"),
    [
        (PUBLIC, "/api/v1/info"),  # an answer
        (PUBLIC, "/api/v1/nothing-here"),  # the router's 404
        (PUBLIC, "/api/v1/me"),  # 401 without a token
        (PUBLIC, "/health"),  # an internal path refused on the public port
        (PUBLIC, "/api/v1/broken"),  # the 500 the request log answers itself
        (INTERNAL, "/health"),
    ],
)
def test_every_answer_carries_the_headers(app: FastAPI, base: str, path: str) -> None:
    with TestClient(app, base_url=base, raise_server_exceptions=False) as client:
        response = client.get(path)

    assert {name: response.headers.get(name) for name in EXPECTED} == EXPECTED


def test_a_route_that_sets_a_policy_of_its_own_keeps_it(app: FastAPI) -> None:
    with TestClient(app, base_url=PUBLIC) as client:
        response = client.get("/api/v1/own-policy")

    assert response.headers.get_list("content-security-policy") == ["default-src 'self'"]
    assert response.headers["x-content-type-options"] == "nosniff"
