"""The object store for coroutines: each call of the blocking store runs in a thread.

Both stores block - the file system store syncs each file to disk, the S3 store waits for the
service - and a held loop answers no request and renews no lease. Errors come through as the
store raised them (ObjectNotFound, InvalidKey, the service's own).
"""

import asyncio
from collections.abc import AsyncIterator

from app.core.storage import ObjectStream, Storage


class AsyncStorage:
    def __init__(self, storage: Storage) -> None:
        self.sync = storage

    async def open_stream(self, key: str) -> tuple[int | None, AsyncIterator[bytes]]:
        """The object's size where the store knows it, and its pieces, each read in a thread;
        ObjectNotFound before any piece. The pieces close the object when they end or stop."""
        stream = await asyncio.to_thread(self.sync.open_stream, key)
        return stream.size, _pieces(stream)

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.sync.put, key, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self.sync.get, key)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self.sync.exists, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.sync.delete, key)


async def _pieces(stream: ObjectStream) -> AsyncIterator[bytes]:
    try:
        while piece := await asyncio.to_thread(next, stream, b""):
            yield piece
    finally:  # a reader gone before the end (a client that hung up) lets the object go too
        stream.close()
