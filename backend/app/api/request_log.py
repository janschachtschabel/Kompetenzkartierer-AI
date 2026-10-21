"""Every request named by ``X-Request-ID`` and written once to the log when it ends.

``RequestLog`` is the outermost middleware: it takes the caller's request id (or makes one) and
the trace headers, adds ``X-Request-ID`` to every answer, and writes one line with method, path,
route template, status and duration. Query values and the client's address stay out of the line:
a search term or a token in a query is the caller's, an address is personal data. A probe that
answers writes no line. An error nothing else handled is logged once with its traceback and
answered with a 500 naming the request id. Each request but a scrape is counted for /metrics.

The method is one of the known ones or ``other``, as in the metrics: h11 takes any token up
to 16 KB, and a long one would split the line in the container log. An error after the answer
began counts as a failed request (500, ``aborted``); uvicorn adds a line of its own then.

A plain ASGI middleware, not Starlette's BaseHTTPMiddleware: that one runs the app in a task
group, and an error came out wrapped in an ExceptionGroup with every frame twice
(compendious-text-fastapi, logging review of 2026-10-08).
"""

import logging
import re
import time
from collections.abc import Sequence
from urllib.parse import quote, unquote_plus

from fastapi.routing import iter_route_contexts
from starlette.datastructures import MutableHeaders
from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.api.internal import INTERNAL_PATHS, METRICS_PATH, REFUSED_INTERNAL
from app.api.paths import route_path
from app.core.logging import set_request_id
from app.core.metrics import bounded_method, observe_request
from app.core.tracing import REQUEST_ID, take_trace_headers

log = logging.getLogger(__name__)

UNMATCHED_ROUTE = "unmatched"  # the raw path of a 404 is caller input
MAX_TARGET_CHARS = 500  # h11 refuses a request head over 16 KB; a line stays readable
MAX_CAUSE_CHARS = 300
_QUERY_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,39}")
INTERNAL_ERROR = "Internal error; please report the request id."


class RequestLog:
    """ASGI middleware; ``routes`` is the application's live route list, for the route template."""

    def __init__(self, app: ASGIApp, routes: Sequence[BaseRoute]) -> None:
        self.app = app
        self.routes = routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = set_request_id(_header(scope, REQUEST_ID))
        take_trace_headers(scope["headers"], request_id)
        asked = dict(scope)  # the request as it came in: the router changes the scope (a mount its root path)
        started = time.perf_counter()
        status = 500  # what the client sees when the app ends without an answer
        answered = aborted = False

        async def named(message: Message) -> None:
            nonlocal status, answered
            if message["type"] == "http.response.start":
                status, answered = message["status"], True
                MutableHeaders(scope=message)[REQUEST_ID] = request_id
            await send(message)

        try:
            await self.app(scope, receive, named)
        except Exception as error:
            cause = " ".join(f"{type(error).__name__}: {error}".split())[:MAX_CAUSE_CHARS]
            method = bounded_method(scope["method"])
            log.exception("unhandled error in %s %s: %s", method, _target(scope), cause)
            if answered:
                # The answer begun cannot be taken back: the client gets a cut-off body, so the
                # request counts as failed, not with the status it started with
                status, aborted = 500, True
            else:
                answer = error_response(500, INTERNAL_ERROR, details={"request_id": request_id})
                await answer(scope, receive, named)
        finally:
            refused = bool(scope.get(REFUSED_INTERNAL))
            self._record(asked, refused, status, aborted, time.perf_counter() - started)

    def _record(self, scope: Scope, refused: bool, status: int, aborted: bool, seconds: float) -> None:
        path = route_path(scope).rstrip("/")
        route = UNMATCHED_ROUTE if refused else route_template(self.routes, scope)
        if path != METRICS_PATH or refused:  # a scrape is no request of the service
            observe_request(scope["method"], route, status, seconds)
        if path in INTERNAL_PATHS and status < 400:
            return
        target = _target(scope)
        method = bounded_method(scope["method"])
        duration_ms = round(seconds * 1000)
        fields: dict[str, object] = {
            "method": method,
            "path": target,
            "route": route,
            "status": status,
            "duration_ms": duration_ms,
        }
        if aborted:
            fields["aborted"] = True
        message = "%s %s %d %d ms" + (" (aborted)" if aborted else "")
        log.info(message, method, target, status, duration_ms, extra={"fields": fields})


def route_template(routes: Sequence[BaseRoute], scope: Scope) -> str:
    """The full template of the route a request was meant for - a bounded label, never the raw path.

    Matched as Starlette's router does: the first full match, else the first partial one (405).
    ``scope`` must be the request as it came in. The route FastAPI leaves in the scope will not
    do: it names the path within its router, without the prefix it was included under, and a
    mounted app counts under its mount path.
    """
    partial: str | None = None
    for context in iter_route_contexts(routes):
        match, _ = context.matches(scope)
        if match is Match.FULL:
            return context.path or UNMATCHED_ROUTE
        if match is Match.PARTIAL and partial is None:
            partial = context.path
    return partial or UNMATCHED_ROUTE


def _target(scope: Scope) -> str:
    """Path and query keys as a line holds them: quoted, so no sign can break or forge a line."""
    keys = _query_keys(scope.get("query_string", b"").decode("latin-1"))
    return (quote(scope["path"]) + (f"?{keys}" if keys else ""))[:MAX_TARGET_CHARS]


def _query_keys(query: str) -> str:
    """The keys of ``key=value`` items that are plain names; ``_`` for any other item.

    An item without ``=`` is a value itself (``?Klimawandel``, ``?<token>``), as is a key that
    reads like text rather than a parameter name.
    """
    keys = []
    for item in query.split("&"):
        if item:
            key, has_value, _ = item.partition("=")
            key = unquote_plus(key)
            keys.append(key if has_value and _QUERY_KEY.fullmatch(key) else "_")
    return "&".join(keys)


def _header(scope: Scope, name: str) -> str | None:
    wanted = name.lower().encode("latin-1")
    for key, value in scope["headers"]:
        if key == wanted:
            return str(value.decode("latin-1"))
    return None
