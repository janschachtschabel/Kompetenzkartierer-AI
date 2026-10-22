"""ASGI middleware: a body over its route's limit is refused before it is read.

FastAPI reads and parses a request's body before it resolves the route's dependencies, the token
check among them: without this, an anonymous caller could make the API read and parse a body of
any size (the old app's audit, E-01). A declared Content-Length over the limit is answered 413
without reading anything; a body that streams past it (chunked, or longer than it said) is cut
there, and the route's reading ends in the same 413.
"""

from collections.abc import Mapping

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.api.paths import route_path

MIB = 2**20
# Every JSON body this API takes is small; the largest are lists of a few hundred entries
JSON_BODY_LIMIT = MIB
TOO_LARGE = "The request body is too large."


class BodyLimit:
    """``default`` bytes for every body, ``limits`` for the routes (method, path) that take more."""

    def __init__(self, app: ASGIApp, default: int, limits: Mapping[tuple[str, str], int]) -> None:
        self.app = app
        self.default = default
        self.limits = dict(limits)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get((scope["method"], route_path(scope)), self.default)
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await error_response(413, TOO_LARGE)(scope, receive, send)
            return
        await self.app(scope, _counting(receive, limit), send)


def _counting(receive: Receive, limit: int) -> Receive:
    """``receive``, cut off once the body passes ``limit`` bytes: raised as the HTTPException
    FastAPI passes through from reading a body, which its handlers answer 413."""
    received = 0

    async def counted() -> Message:
        nonlocal received
        message = await receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                raise HTTPException(413, TOO_LARGE)
        return message

    return counted
