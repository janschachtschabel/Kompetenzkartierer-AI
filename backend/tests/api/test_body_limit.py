"""A body over its route's limit is refused before it is read; one that streams past it is cut.

FastAPI reads and parses a body before it resolves the route's dependencies - the token check
among them - so without this an anonymous caller could make the API read and parse a body of any
size (the old app's audit, E-01).
"""

from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.app import create_app
from app.api.body_limit import JSON_BODY_LIMIT, BodyLimit
from app.api.errors import install_error_handlers
from tests.support import make_settings

PUBLIC = "http://testserver:8000"


class Spy:
    """Notes each request that gets past the limit into the application."""

    def __init__(self, app: ASGIApp, reached: list[str]) -> None:
        self.app = app
        self.reached = reached

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            self.reached.append(scope["path"])
        await self.app(scope, receive, send)


def mini_app(read: list[int], reached: list[str] | None = None) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        read.append(len(body))
        return {"read": len(body)}

    app.add_api_route("/echo", echo, methods=["POST"])
    app.add_api_route("/upload", echo, methods=["POST"])
    app.add_middleware(Spy, reached=[] if reached is None else reached)
    app.add_middleware(BodyLimit, default=10, limits={("POST", "/upload"): 100})
    return app


def chunks(size: int, parts: int) -> Iterator[bytes]:
    # sent as it comes, without Content-Length: only counting finds where it ends
    for _ in range(parts):
        yield b"x" * size


def test_a_body_declared_too_large_is_refused_unread() -> None:
    read: list[int] = []
    reached: list[str] = []
    with TestClient(mini_app(read, reached)) as client:
        answer = client.post("/echo", content=b"x" * 11)

    assert answer.status_code == 413
    assert answer.json()["code"] == "content_too_large"
    assert reached == []  # the application never saw it, so nothing of it was read


def test_a_body_that_streams_past_the_limit_is_cut() -> None:
    read: list[int] = []
    with TestClient(mini_app(read)) as client:
        answer = client.post("/echo", content=chunks(6, 2))

    assert answer.status_code == 413
    assert read == []


def test_a_body_within_the_limit_is_read() -> None:
    read: list[int] = []
    with TestClient(mini_app(read)) as client:
        answer = client.post("/echo", content=b"x" * 10)

    assert answer.json() == {"read": 10}


def test_a_route_with_a_limit_of_its_own_takes_more() -> None:
    read: list[int] = []
    with TestClient(mini_app(read)) as client:
        within = client.post("/upload", content=chunks(10, 10))
        past = client.post("/upload", content=b"x" * 101)

    assert within.json() == {"read": 100}
    assert past.status_code == 413


def test_the_api_refuses_a_large_body_before_it_asks_for_the_token() -> None:
    with TestClient(create_app(make_settings()), base_url=PUBLIC) as client:
        answer = client.post(
            "/api/v1/accounts",
            content=b"{" + b" " * JSON_BODY_LIMIT + b"}",
            headers={"Content-Type": "application/json"},
        )

    assert answer.status_code == 413
