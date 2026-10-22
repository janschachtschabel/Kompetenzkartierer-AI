"""Every request named by ``X-Request-ID`` and written once to the log when it ends.

``RequestLog`` is the outermost middleware but SecurityHeaders: it takes the caller's request
id (or makes one) and the trace headers, adds ``X-Request-ID`` to every answer, and writes one
line with method, path, route template, status and duration. Query values and the client's
address stay out of the line: a search term or a token in a query is the caller's, an address is
personal data; of the query only the names the route declares are written, any other item as
``_``. A probe that answers
writes no line. An error nothing else handled is logged once with its traceback and
answered with a 500 naming the request id. Each request but a scrape is counted for /metrics.

The method is one of the known ones or ``other``, as in the metrics: h11 takes long tokens
(tens of KB arrive in one read), and a long one would split the line in the container log. An
error after the answer began and before its body was complete counts as a failed request (500,
``aborted``); uvicorn adds a line of its own then. An error after a complete answer - a
background task - is logged, the request keeps its status.

A plain ASGI middleware, not Starlette's BaseHTTPMiddleware: that one runs the app in a task
group, and an error came out wrapped in an ExceptionGroup with every frame twice
(compendious-text-fastapi, logging review of 2026-10-08).
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote, unquote_plus

from starlette.datastructures import MutableHeaders
from starlette.routing import BaseRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.api.internal import INTERNAL_PATHS, METRICS_PATH, REFUSED_INTERNAL
from app.api.paths import route_path
from app.api.route_index import UNMATCHED_ROUTE, RouteIndex
from app.core.logging import set_request_id
from app.core.metrics import bounded_method, observe_request
from app.core.tracing import REQUEST_ID, take_trace_headers

log = logging.getLogger(__name__)

MAX_TARGET_CHARS = 500  # path and query names in a line; a line stays readable
MAX_CAUSE_CHARS = 300
INTERNAL_ERROR = "Internal error; please report the request id."


@dataclass(frozen=True)
class _Asked:
    """What the line says about the request, taken before the router changes the scope."""

    method: str
    path: str  # without the root path and a trailing slash, for the probe and scrape checks
    route: str
    target: str


class RequestLog:
    """ASGI middleware; ``routes`` is the application's live route list, for the route template."""

    def __init__(self, app: ASGIApp, routes: Sequence[BaseRoute]) -> None:
        self.app = app
        self.index = RouteIndex(routes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = set_request_id(_header(scope, REQUEST_ID))
        take_trace_headers(scope["headers"], request_id)
        matched = self.index.match(scope)
        asked = _Asked(
            method=bounded_method(scope["method"]),
            path=route_path(scope).rstrip("/"),
            route=matched.template,
            target=_target(scope, matched.query_names),
        )
        started = time.perf_counter()
        status = 500  # what the client sees when the app ends without an answer
        answered = completed = aborted = False

        async def named(message: Message) -> None:
            nonlocal status, answered, completed
            if message["type"] == "http.response.start":
                status, answered = message["status"], True
                MutableHeaders(scope=message)[REQUEST_ID] = request_id
            elif message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True
            await send(message)

        try:
            await self.app(scope, receive, named)
        except Exception as error:
            cause = " ".join(f"{type(error).__name__}: {error}".split())[:MAX_CAUSE_CHARS]
            log.exception("unhandled error in %s %s: %s", asked.method, asked.target, cause)
            if not answered:
                answer = error_response(500, INTERNAL_ERROR, details={"request_id": request_id})
                await answer(scope, receive, named)
            elif not completed:
                # The answer begun cannot be taken back: the client gets a cut-off body, so the
                # request counts as failed, not with the status it started with
                status, aborted = 500, True
        finally:
            refused = bool(scope.get(REFUSED_INTERNAL))
            self._record(asked, refused, status, aborted, time.perf_counter() - started)

    def _record(self, asked: _Asked, refused: bool, status: int, aborted: bool, seconds: float) -> None:
        route = UNMATCHED_ROUTE if refused else asked.route
        if asked.path != METRICS_PATH or refused:  # a scrape is no request of the service
            observe_request(asked.method, route, status, seconds)
        if asked.path in INTERNAL_PATHS and status < 400:
            return
        duration_ms = round(seconds * 1000)
        fields: dict[str, object] = {
            "method": asked.method,
            "path": asked.target,
            "route": route,
            "status": status,
            "duration_ms": duration_ms,
        }
        if aborted:
            fields["aborted"] = True
        message = "%s %s %d %d ms" + (" (aborted)" if aborted else "")
        log.info(message, asked.method, asked.target, status, duration_ms, extra={"fields": fields})


def _target(scope: Scope, query_names: frozenset[str]) -> str:
    """Path and query as a line holds them: quoted, so no sign can break or forge a line.

    Of the query only the names the route declares; ``_`` for any other item, as it may be a
    value itself (``?Klimawandel``, ``?<token>``, a padded token that reads like ``key=``).
    """
    items = []
    for item in scope.get("query_string", b"").decode("latin-1").split("&"):
        if item:
            key, has_value, _ = item.partition("=")
            name = unquote_plus(key)
            items.append(name if has_value and name in query_names else "_")
    query = "&".join(items)
    return (quote(scope["path"]) + (f"?{query}" if query else ""))[:MAX_TARGET_CHARS]


def _header(scope: Scope, name: str) -> str | None:
    wanted = name.lower().encode("latin-1")
    for key, value in scope["headers"]:
        if key == wanted:
            return str(value.decode("latin-1"))
    return None
