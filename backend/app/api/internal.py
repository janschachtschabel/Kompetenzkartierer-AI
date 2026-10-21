"""Paths for the cluster: probes and metrics, answered on the internal port only.

The ingress releases the public port; the internal one stays inside the cluster. On the public
port an internal path answers 404 as if it did not exist, also with a trailing slash (the
router's redirect would otherwise confirm it) and under a root path.
"""

from fastapi import APIRouter, Request, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import error_response
from app.api.paths import route_path
from app.core import metrics

METRICS_PATH = "/metrics"
INTERNAL_PATHS = frozenset({"/health", "/ready", METRICS_PATH})
# Set in the scope of a request refused here: the metrics count it unmatched, not as traffic of the path
REFUSED_INTERNAL = "kka.refused_internal"

router = APIRouter(include_in_schema=False)


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process answers. The database is a matter for /ready."""
    return {"status": "ok"}


@router.get(METRICS_PATH)
async def scrape(request: Request) -> Response:
    content, content_type = metrics.render(request.headers.get("accept", ""))
    return Response(content=content, media_type=content_type)


def is_internal(path: str) -> bool:
    return path.rstrip("/") in INTERNAL_PATHS


class InternalOnly:
    """ASGI middleware: 404 for an internal path asked on any port but ``port``."""

    def __init__(self, app: ASGIApp, port: int) -> None:
        self.app = app
        self.port = port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and is_internal(route_path(scope)) and _server_port(scope) != self.port:
            scope[REFUSED_INTERNAL] = True
            await error_response(404)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _server_port(scope: Scope) -> int | None:
    """The port of the socket the request came in on, not what a proxy or the Host header says.

    ``None`` without a server or on a unix socket, whose port ASGI leaves ``None``.
    """
    server = scope.get("server")
    return int(server[1]) if server and server[1] is not None else None
