"""A download the client leaves: the stored object is let go however the sending ends.

The route is driven as an ASGI server drives it, in the TestClient's own loop: a client gone
before the first piece, gone while a piece is being sent (ASGI 2.3: the streaming task is
cancelled), or a send that raises (ASGI 2.4). Each leaves the object closed at once, not when
the garbage collector comes by: an open file, or an S3 body that holds its pooled connection.
"""

import asyncio
import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Send

from app.api.app import create_app
from app.core.storage import FileSystemStorage, ObjectStream
from app.core.storage_async import AsyncStorage
from app.db.migrate import migrate
from app.db.sources import StoredFile, record_upload
from tests.support import make_settings, seed_account, selector_client

pytestmark = pytest.mark.pg

PUBLIC = "http://testserver:8000"
KEY = "sources/" + "08" * 32
BIG = b"%PDF-1.7 " + b"x" * (3 * 2**20)  # four pieces of a MiB at most


class NotingStore(FileSystemStorage):
    """A file system store that keeps every stream it opened, to look at them after."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.opened: list[ObjectStream] = []

    def open_stream(self, key: str) -> ObjectStream:
        stream = super().open_stream(key)
        self.opened.append(stream)
        return stream


@pytest.fixture
def entry(database_url: str, tmp_path: Path) -> Iterator[tuple[TestClient, NotingStore, str, dict[str, str]]]:
    """An account's upload of a file of four pieces, and a client of the app it is served by."""
    migrate(database_url)
    owner_id, header = seed_account(database_url, "Lehrkraft", ["nutzer"])
    store = NotingStore(tmp_path / "store")
    store.put(KEY, BIG)
    stored = StoredFile(sha256=b"\x08" * 32, size=len(BIG), mime="application/pdf", storage_key=KEY)

    async def fill() -> UUID:
        async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as connection:
            names = {"file_name": "lp.pdf", "received_name": "lp.pdf", "title": "LP"}
            return await record_upload(connection, owner=owner_id, stored=stored, **names)

    source_id = asyncio.run(fill(), loop_factory=asyncio.SelectorEventLoop)
    app = create_app(make_settings(database_url=database_url, storage_dir=tmp_path / "store"))
    with selector_client(app, base_url=PUBLIC) as client:
        app.state.storage = AsyncStorage(store)
        yield client, store, f"/api/v1/sources/{source_id}/file", header


def drive(
    client: TestClient,
    path: str,
    header: dict[str, str],
    spec: str,
    receive: Receive,
    send: Send,
) -> None:
    """The app's answer to a GET of ``path``, through ``receive`` and ``send`` as a server's."""
    headers = [(b"host", b"testserver:8000")] + [(k.lower().encode(), v.encode()) for k, v in header.items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 8000),
        "state": {},
    }

    async def answer() -> None:
        # a client gone may end the answer in an error; what the tests look at is the store
        with contextlib.suppress(Exception):
            await client.app(scope, receive, send)

    assert client.portal is not None
    client.portal.call(answer)


async def gone() -> Message:
    return {"type": "http.disconnect"}


def test_a_client_gone_before_the_first_piece_lets_the_object_go(entry: Any) -> None:
    client, store, path, header = entry

    async def held(message: Message) -> None:  # the head of the answer waits for the client
        await asyncio.Event().wait()

    drive(client, path, header, "2.3", gone, held)

    assert [stream.closed for stream in store.opened] == [True]


def test_a_client_gone_while_a_piece_is_sent_lets_the_object_go(entry: Any) -> None:
    client, store, path, header = entry
    in_send = asyncio.Event()
    bodies: list[bytes] = []

    async def leaving() -> Message:
        await in_send.wait()
        return {"type": "http.disconnect"}

    async def slow(message: Message) -> None:  # the first piece goes out, the second one waits
        if message["type"] == "http.response.body":
            bodies.append(message["body"])
            if len(bodies) == 2:
                in_send.set()
                await asyncio.Event().wait()

    drive(client, path, header, "2.3", leaving, slow)

    assert len(bodies) == 2
    assert [stream.closed for stream in store.opened] == [True]


def test_a_send_that_fails_lets_the_object_go(entry: Any) -> None:
    # ASGI 2.4: the server raises OSError from send once the client is gone
    client, store, path, header = entry

    async def failing(message: Message) -> None:
        if message["type"] == "http.response.body":
            raise OSError("the client is gone")

    async def waiting() -> Message:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    drive(client, path, header, "2.4", waiting, failing)

    assert [stream.closed for stream in store.opened] == [True]


def test_a_download_read_to_its_end_lets_the_object_go(entry: Any) -> None:
    client, store, path, header = entry

    answer = client.get(path, headers=header)

    assert answer.content == BIG
    assert [stream.closed for stream in store.opened] == [True]
