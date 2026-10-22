"""A stored object sent as a download, let go however the sending ends.

A client that hangs up cancels the streaming task (ASGI 2.3) or makes send raise (2.4); either
leaves the object's reader suspended where it was, and nothing closes the object but the
garbage collector - an open file, or an S3 body that holds its pooled connection.
"""

import anyio
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.core.storage_async import AsyncObjectStream


class ObjectDownload(StreamingResponse):
    def __init__(self, stream: AsyncObjectStream, *, media_type: str, headers: dict[str, str]) -> None:
        super().__init__(stream, media_type=media_type, headers=headers)
        self.stream = stream

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):  # closed even while the request is being cancelled
                await self.stream.aclose()
