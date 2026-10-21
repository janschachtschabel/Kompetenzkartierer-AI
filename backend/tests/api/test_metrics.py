"""HTTP metrics by route template, scraped on the internal port only."""

from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.api.app import create_app
from tests.support import make_settings

PUBLIC = "http://testserver:8000"
INTERNAL = "http://testserver:9000"
REQUESTS = "kka_http_requests_total"
DURATION_COUNT = "kka_http_request_duration_seconds_count"


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def app() -> FastAPI:
    application = create_app(make_settings())

    async def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    application.add_api_route("/api/v1/items/{item_id}", item, tags=["system"])
    return application


@pytest.fixture
def public(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=PUBLIC) as client:
        yield client


@pytest.fixture
def internal(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=INTERNAL) as client:
        yield client


def test_metrics_answer_on_the_internal_port_in_the_text_format(internal: TestClient) -> None:
    response = internal.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert f"# TYPE {REQUESTS} counter" in response.text


def test_metrics_follow_the_scrapers_accept_header(internal: TestClient) -> None:
    response = internal.get("/metrics", headers={"Accept": "application/openmetrics-text; version=1.0.0"})

    assert response.headers["content-type"].startswith("application/openmetrics-text")
    assert response.text.endswith("# EOF\n")


def test_metrics_do_not_exist_on_the_public_port(public: TestClient) -> None:
    assert public.get("/metrics").status_code == 404


def test_a_request_is_counted_by_its_route_template(public: TestClient) -> None:
    labels = {"method": "GET", "route": "/api/v1/items/{item_id}"}
    before = sample(REQUESTS, status="200", **labels)
    durations = sample(DURATION_COUNT, **labels)

    public.get("/api/v1/items/42")
    public.get("/api/v1/items/43")

    assert sample(REQUESTS, status="200", **labels) == before + 2
    assert sample(DURATION_COUNT, **labels) == durations + 2
    assert sample(REQUESTS, method="GET", route="/api/v1/items/42", status="200") == 0


def test_a_path_no_route_takes_shares_one_label(public: TestClient) -> None:
    before = sample(REQUESTS, method="GET", route="unmatched", status="404")

    public.get("/api/v1/random-1")
    public.get("/api/v1/random-2")

    assert sample(REQUESTS, method="GET", route="unmatched", status="404") == before + 2


def test_an_invented_method_shares_one_label(public: TestClient) -> None:
    before = sample(REQUESTS, method="other", route="/api/v1/info", status="405")

    public.request("FOO", "/api/v1/info")

    assert sample(REQUESTS, method="other", route="/api/v1/info", status="405") == before + 1


def test_a_refused_internal_path_is_no_traffic_of_that_path(public: TestClient) -> None:
    before = sample(REQUESTS, method="GET", route="/health", status="404")
    unmatched = sample(REQUESTS, method="GET", route="unmatched", status="404")

    public.get("/health")

    assert sample(REQUESTS, method="GET", route="/health", status="404") == before
    assert sample(REQUESTS, method="GET", route="unmatched", status="404") == unmatched + 1


def test_a_scrape_is_not_counted(internal: TestClient) -> None:
    internal.get("/metrics")
    internal.get("/metrics")

    assert sample(REQUESTS, method="GET", route="/metrics", status="200") == 0


@pytest.fixture
def routed() -> Iterator[TestClient]:
    """Routers included the usual FastAPI ways: with a prefix, nested, and a mounted app."""
    application = create_app(make_settings())
    items = APIRouter()

    @items.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    application.include_router(items, prefix="/api/v1/a", tags=["system"])
    application.include_router(items, prefix="/api/v1/b", tags=["system"])
    inner = APIRouter(prefix="/inner")

    @inner.get("/deep/{x}")
    async def deep(x: str) -> dict[str, str]:
        return {"x": x}

    outer = APIRouter(prefix="/api/v1/outer")
    outer.include_router(inner)
    application.include_router(outer, tags=["system"])

    async def hello(request: Request) -> PlainTextResponse:
        return PlainTextResponse(request.path_params["name"])

    application.mount("/files", Starlette(routes=[Route("/hello/{name}", hello)]))
    with TestClient(application, base_url=PUBLIC) as client:
        yield client


@pytest.mark.parametrize(
    ("path", "status", "route"),
    [
        ("/api/v1/a/items/1", "200", "/api/v1/a/items/{item_id}"),
        ("/api/v1/b/items/2", "200", "/api/v1/b/items/{item_id}"),
        ("/api/v1/outer/inner/deep/abc", "200", "/api/v1/outer/inner/deep/{x}"),
        ("/files/hello/bob", "200", "/files"),
        ("/files/nothing-here", "404", "/files"),
    ],
)
def test_the_label_is_the_full_template_of_the_route(
    routed: TestClient, path: str, status: str, route: str
) -> None:
    before = sample(REQUESTS, method="GET", route=route, status=status)

    routed.get(path)

    assert sample(REQUESTS, method="GET", route=route, status=status) == before + 1


def test_a_refused_metrics_path_counts_as_unmatched(public: TestClient) -> None:
    before = sample(REQUESTS, method="GET", route="unmatched", status="404")

    public.get("/metrics")

    assert sample(REQUESTS, method="GET", route="unmatched", status="404") == before + 1
