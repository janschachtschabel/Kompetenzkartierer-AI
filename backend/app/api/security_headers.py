"""The headers every answer of the API carries for a browser that might render it.

In Compose the web server sets them; in a cluster the ingress hands /api/v1 straight to the
API, so the API sets them itself. It answers JSON only: nothing may be loaded into it, nothing
may frame it. A route that sets one of these headers (an export to be shown, M1) keeps its own.
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class SecurityHeaders:
    """ASGI middleware; the outermost one, so the answers the others make carry the headers too."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, with_headers)
