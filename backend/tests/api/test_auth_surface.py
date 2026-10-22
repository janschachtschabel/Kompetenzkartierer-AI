"""What the auth layer shows outward: guarded routes, the spec, clean input, a database away."""

import time
from typing import Any

import pytest
from fastapi.routing import APIRoute, iter_route_contexts

from app.api.app import create_app
from app.api.deps import principal
from app.db.migrate import migrate
from tests.support import make_settings, seed_admin, selector_client

PUBLIC = "http://testserver:8000"
# The operations a visitor may call without a token at any PUBLIC_ACCESS
OPEN_OPERATIONS = {("GET", "/api/v1/info")}


def depends_on(dependant: Any, call: object) -> bool:
    return dependant.call is call or any(depends_on(sub, call) for sub in dependant.dependencies)


def test_every_api_operation_but_the_open_ones_asks_who_calls() -> None:
    # authentication is per route: a router that forgets it would be public, LLM routes too
    app = create_app(make_settings())
    unguarded = []
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        path = context.path or ""
        if not isinstance(route, APIRoute) or not path.startswith("/api/v1"):
            continue
        for method in sorted(route.methods or ()):
            if (method, path) not in OPEN_OPERATIONS and not depends_on(route.dependant, principal):
                unguarded.append(f"{method} {path}")

    assert unguarded == []


def test_the_spec_names_the_bearer_scheme_and_the_refusals() -> None:
    spec = create_app(make_settings()).openapi()

    assert spec["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    answers = spec["paths"]["/api/v1/accounts"]["post"]["responses"]
    for status in ("401", "403", "429"):
        assert answers[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorBody"
        }


def test_a_database_away_answers_503_soon(restore_logging: None) -> None:
    app = create_app(make_settings(database_url="postgresql://kka:fake@127.0.0.1:1/kka", db_pool_timeout_s=1))
    with selector_client(app, base_url=PUBLIC) as client:
        started = time.monotonic()
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer kka_" + "x" * 43})
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
    assert int(response.headers["Retry-After"]) > 0
    assert elapsed < 5


@pytest.mark.pg
@pytest.mark.parametrize(
    "name",
    ["Admin" + chr(0x00), "Ad" + chr(0x200B) + "min", "Admin" + chr(0x202E), "Lehr" + chr(0x0A) + "kraft"],
    ids=["nul", "zero-width", "bidi", "newline"],
)
def test_an_account_name_with_hidden_signs_is_refused(database_url: str, name: str) -> None:
    migrate(database_url)
    app = create_app(make_settings(database_url=database_url))
    with selector_client(app, base_url=PUBLIC) as client:
        admin = seed_admin(database_url)
        response = client.post("/api/v1/accounts", json={"name": name, "roles": ["nutzer"]}, headers=admin)

    assert response.status_code == 422


@pytest.mark.pg
def test_a_name_written_two_ways_is_one_name(database_url: str) -> None:
    migrate(database_url)
    app = create_app(make_settings(database_url=database_url))
    with selector_client(app, base_url=PUBLIC) as client:
        admin = seed_admin(database_url)
        composed = client.post(
            "/api/v1/accounts", json={"name": "J" + chr(0xFC) + "rgen", "roles": ["nutzer"]}, headers=admin
        )
        decomposed = client.post(
            "/api/v1/accounts", json={"name": "Ju" + chr(0x308) + "rgen", "roles": ["nutzer"]}, headers=admin
        )

    assert composed.status_code == 201
    assert decomposed.status_code == 409
