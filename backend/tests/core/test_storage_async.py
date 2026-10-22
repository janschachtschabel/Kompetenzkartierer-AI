"""The store for coroutines: a call of the blocking store runs in a thread, never in the loop.

A held loop answers no request and renews no lease; a file's fsync or an S3 request takes long
enough for that.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from app.core.storage import FileSystemStorage, ObjectNotFound
from app.core.storage_async import AsyncStorage
from tests.support import loop_watch

SLOW_S = 0.4


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine, loop_factory=asyncio.SelectorEventLoop)


class SlowStore:
    """Each call holds its thread, as a slow disk or service would."""

    def put(self, key: str, data: bytes) -> None:
        time.sleep(SLOW_S)

    def get(self, key: str) -> bytes:
        time.sleep(SLOW_S)
        return b""

    def exists(self, key: str) -> bool:
        time.sleep(SLOW_S)
        return True

    def delete(self, key: str) -> None:
        time.sleep(SLOW_S)


def test_the_calls_reach_the_store(tmp_path: Path) -> None:
    store = AsyncStorage(FileSystemStorage(tmp_path))

    async def calls() -> tuple[bool, bytes]:
        await store.put("sources/ab.txt", b"text")
        return await store.exists("sources/ab.txt"), await store.get("sources/ab.txt")

    assert run(calls()) == (True, b"text")
    run(store.delete("sources/ab.txt"))
    assert not (tmp_path / "sources" / "ab.txt").exists()


def test_the_store_s_errors_come_through_as_they_are(tmp_path: Path) -> None:
    with pytest.raises(ObjectNotFound):
        run(AsyncStorage(FileSystemStorage(tmp_path)).get("sources/missing.txt"))


@pytest.mark.parametrize("call", ["put", "get", "exists", "delete"])
def test_a_slow_store_does_not_hold_the_loop(call: str) -> None:
    store = AsyncStorage(SlowStore())
    calls: dict[str, Callable[[], Awaitable[object]]] = {
        "put": lambda: store.put("a", b"x"),
        "get": lambda: store.get("a"),
        "exists": lambda: store.exists("a"),
        "delete": lambda: store.delete("a"),
    }

    async def measured() -> float:
        async with loop_watch() as longest:
            await calls[call]()
        return longest[0]

    assert run(measured()) < SLOW_S / 2
