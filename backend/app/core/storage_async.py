"""The object store for coroutines: each call of the blocking store runs in a thread.

Both stores block - the file system store syncs each file to disk, the S3 store waits for the
service - and a held loop answers no request and renews no lease. Errors come through as the
store raised them (ObjectNotFound, InvalidKey, the service's own).
"""

import asyncio
from collections.abc import AsyncIterator

from app.core.storage import ObjectStream, Storage


class AsyncObjectStream:
    """An object read in pieces for coroutines, each piece read in a thread, with its size where
    the store knows it. Read to its end it closes itself; whoever opened it calls ``aclose``
    however the reading ended - a generator's ``finally`` would not run for a reader that was
    cancelled while it held a piece, or before it asked for the first."""

    def __init__(self, stream: ObjectStream) -> None:
        self.size = stream.size
        self._stream = stream

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self._pieces()

    async def _pieces(self) -> AsyncIterator[bytes]:
        while piece := await asyncio.to_thread(next, self._stream, b""):
            yield piece

    async def aclose(self) -> None:
        """Let the object go (a file, an S3 body holding its pooled connection); once is enough."""
        await asyncio.to_thread(self._stream.close)


class AsyncStorage:
    def __init__(self, storage: Storage) -> None:
        self.sync = storage

    async def open_stream(self, key: str) -> AsyncObjectStream:
        """The object to read in pieces; ObjectNotFound before any piece."""
        return AsyncObjectStream(await asyncio.to_thread(self.sync.open_stream, key))

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.sync.put, key, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self.sync.get, key)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self.sync.exists, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.sync.delete, key)
