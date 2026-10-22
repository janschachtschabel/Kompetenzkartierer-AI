"""Reading an answer no further than a limit, unpacking it within the limit.

httpx inflated each chunk it received in one piece, and only then could the size be counted: 822
bytes of gzip became 840 MiB before the limit was looked at (the old app's audit, G-01). The body
is read raw and unpacked a piece at a time; one layer of gzip or deflate, nothing else. Taken over
from curriculum-extractor (tests/test_http_body.py), for the async reader.
"""

import tracemalloc
from collections.abc import Mapping, Sequence

import httpx2
import pytest

from app.sources.http_body import BodyTooLarge, UnsupportedEncoding, aread_body
from tests.sources.compressed import CHUNK, MIB, arriving, gzip_bomb, in_chunks, packed

pytestmark = pytest.mark.anyio

BASE = "https://example.test"
LIMIT = 4 * MIB
# Long enough to span several pieces of the reader and many chunks below
TEXT = ("Die Lernenden beschreiben Zusammenhänge zwischen Ursache und Wirkung. " * 3_000).encode()
Headers = Mapping[str, str] | Sequence[tuple[str, str]]


async def read(content: list[bytes] | bytes, headers: Headers, limit: int) -> bytes:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = content if isinstance(content, bytes) else arriving(content)
        return httpx2.Response(200, content=body, headers=headers)

    async with (
        httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client,
        client.stream("GET", BASE) as response,
    ):
        return await aread_body(response, limit)


async def test_an_answer_unpacking_far_past_the_limit_is_stopped_holding_no_more_than_the_limit() -> None:
    raw = in_chunks(gzip_bomb())  # built before the measurement: the bomb is the server's

    tracemalloc.start()
    try:
        with pytest.raises(BodyTooLarge):
            await read(raw, {"Content-Encoding": "gzip"}, LIMIT)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < LIMIT + 8 * CHUNK, f"{peak / MIB:.1f} MiB held for a limit of {LIMIT / MIB:.0f} MiB"


@pytest.mark.parametrize(
    ("encoding", "packing"),
    [
        ("gzip", "gzip"),
        ("x-gzip", "x-gzip"),
        ("GZip", "gzip"),
        ("deflate", "deflate"),
        ("deflate", "raw deflate"),
        ("identity", "identity"),
        (None, "identity"),
    ],
)
async def test_an_answer_packed_as_asked_is_unpacked(encoding: str | None, packing: str) -> None:
    headers = {"Content-Encoding": encoding} if encoding else {}

    # small chunks: a piece boundary inside the header and inside the stream
    assert await read(in_chunks(packed(TEXT, packing), 1_000), headers, LIMIT) == TEXT


async def test_the_limit_counts_the_unpacked_bytes() -> None:
    wire = in_chunks(packed(TEXT, "gzip"), 1_000)

    assert await read(wire, {"Content-Encoding": "gzip"}, len(TEXT)) == TEXT
    with pytest.raises(BodyTooLarge):
        await read(wire, {"Content-Encoding": "gzip"}, len(TEXT) - 1)


async def test_what_follows_the_end_of_the_stream_is_dropped_but_counted() -> None:
    # zlib keeps whatever follows the end of a stream, and a server could go on sending it for ever
    stream = packed(TEXT, "gzip")

    assert await read(in_chunks(stream + b"\x00" * 10, 1_000), {"Content-Encoding": "gzip"}, LIMIT) == TEXT
    with pytest.raises(BodyTooLarge):
        await read([stream, *in_chunks(bytes(LIMIT))], {"Content-Encoding": "gzip"}, LIMIT)


async def test_an_answer_read_already_is_held_to_the_limit_as_it_is() -> None:
    # httpx2 reads a response built from bytes as soon as it is made: nothing raw is left
    body = packed(TEXT, "gzip")

    assert await read(body, {}, len(body)) == body
    with pytest.raises(BodyTooLarge):
        await read(body, {}, len(body) - 1)


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Encoding": "gzip, gzip"},
        {"Content-Encoding": "deflate,gzip"},
        [("Content-Encoding", "gzip"), ("Content-Encoding", "gzip")],
        {"Content-Encoding": "br"},
        {"Content-Encoding": "zstd"},
        {"Content-Encoding": "compress"},
    ],
    ids=["stacked", "stacked-without-space", "two-headers", "br", "zstd", "compress"],
)
async def test_an_answer_packed_twice_or_in_an_unknown_way_is_refused(headers: Headers) -> None:
    with pytest.raises(UnsupportedEncoding):
        await read([packed(packed(TEXT, "gzip"), "gzip")], headers, LIMIT)


async def test_a_broken_compressed_answer_is_a_decoding_error() -> None:
    with pytest.raises(httpx2.DecodingError):
        await read([b"not gzip at all"], {"Content-Encoding": "gzip"}, LIMIT)
