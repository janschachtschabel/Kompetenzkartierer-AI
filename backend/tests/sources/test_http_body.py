"""Reading an answer no further than a limit, unpacking it within the limit.

httpx inflated each chunk it received in one piece, and only then could the size be counted: 822
bytes of gzip became 840 MiB before the limit was looked at (the old app's audit, G-01). The body
is read raw and unpacked a piece at a time; one layer of gzip or deflate, nothing else. Taken over
from curriculum-extractor (tests/test_http_body.py), for the async reader.
"""

import random
import tracemalloc
import zlib
from collections.abc import Callable, Mapping, Sequence

import httpx2
import pytest

from app.sources.http_body import BodyTooLarge, BrokenCompression, UnsupportedEncoding, aread_body
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


@pytest.mark.parametrize(
    "wire",
    [[b"not gzip at all"], [packed(b"%PDF-1.7 ", "gzip"), b"\x1f\x8b" + b"X" * 20]],
    ids=["no-gzip", "broken-second-member"],
)
async def test_a_broken_compressed_answer_cannot_be_unpacked(wire: list[bytes]) -> None:
    # the same bytes again at the next attempt: not the DecodingError of a transfer cut short
    with pytest.raises(BrokenCompression):
        await read(wire, {"Content-Encoding": "gzip"}, LIMIT)


@pytest.mark.parametrize(
    ("encoding", "packing"), [("gzip", "gzip"), ("deflate", "deflate"), ("deflate", "raw deflate")]
)
async def test_a_compressed_answer_that_breaks_off_is_a_decoding_error(encoding: str, packing: str) -> None:
    # half a file kept as the whole would be acquired as the document
    wire = packed(TEXT, packing)

    with pytest.raises(httpx2.DecodingError):
        await read(in_chunks(wire[: len(wire) // 2], 1_000), {"Content-Encoding": encoding}, LIMIT)


async def test_an_empty_compressed_answer_is_empty() -> None:
    # nothing came that could break off
    assert await read([], {"Content-Encoding": "gzip"}, LIMIT) == b""


@pytest.mark.parametrize("size", [1_000, 1], ids=["chunks", "byte-by-byte-at-the-seam"])
async def test_a_gzip_answer_of_several_members_is_unpacked_whole(size: int) -> None:
    # gzip allows members one after another (RFC 1952); the first alone is part of the file
    first, second = TEXT[:5_000], TEXT[5_000:]
    wire = packed(first, "gzip") + packed(second, "gzip")
    seam = len(packed(first, "gzip"))
    chunks = [*in_chunks(wire[: seam - 2], 1_000), *in_chunks(wire[seam - 2 : seam + 2], size)]
    chunks += in_chunks(wire[seam + 2 :], 1_000)

    assert await read(chunks, {"Content-Encoding": "gzip"}, LIMIT) == TEXT


def _empty_members(size: int) -> bytes:
    empty = packed(b"", "gzip")
    return empty * (size // len(empty))


def _empty_blocks(size: int) -> bytes:
    # one member of empty stored blocks, as a sync flush writes them
    packer = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    head = packer.compress(b"") + packer.flush(zlib.Z_SYNC_FLUSH)
    empty_block = b"\x00\x00\x00\xff\xff"
    return head + empty_block * (size // len(empty_block))


@pytest.mark.parametrize("wire", [_empty_members, _empty_blocks], ids=["empty-members", "empty-blocks"])
async def test_an_answer_unpacking_to_nothing_is_held_to_the_limit_by_its_weight(
    wire: Callable[[int], bytes],
) -> None:
    # nothing unpacked counts: without a bound on the bytes received, the worker unpacked for as
    # long as the server sent, until the fetch's deadline, three times
    with pytest.raises(BodyTooLarge):
        await read(in_chunks(wire(2 * MIB)), {"Content-Encoding": "gzip"}, MIB)


async def test_an_incompressible_file_at_the_limit_passes_packed() -> None:
    # packing adds a little to what does not shrink; the bound on the bytes received allows it
    data = random.Random(7).randbytes(256 * 1024)  # noqa: S311 - test data, seeded to repeat
    wire = zlib.compress(data, 9, 16 + zlib.MAX_WBITS)

    assert len(wire) > len(data)
    assert await read(in_chunks(wire), {"Content-Encoding": "gzip"}, len(data)) == data


async def test_a_file_packed_with_frequent_flushes_passes_at_the_limit() -> None:
    # a server that flushes every 512 bytes adds a block's few bytes each time, some 2 % on what
    # does not shrink: the bound on the bytes received is there for empty members, not for this
    data = random.Random(11).randbytes(256 * 1024)  # noqa: S311 - test data, seeded to repeat
    packer = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    pieces = [
        packer.compress(data[at : at + 512]) + packer.flush(zlib.Z_SYNC_FLUSH)
        for at in range(0, len(data), 512)
    ]
    wire = b"".join(pieces) + packer.flush()

    assert len(wire) > len(data) * 1.015
    assert await read(in_chunks(wire), {"Content-Encoding": "gzip"}, len(data)) == data


async def test_a_later_gzip_member_is_held_to_the_limit_with_the_first() -> None:
    # each member below the limit, together past it: the count runs on across members
    member = packed(bytes(LIMIT * 6 // 10), "gzip")
    raw = [*in_chunks(member), *in_chunks(member)]

    tracemalloc.start()
    try:
        with pytest.raises(BodyTooLarge):
            await read(raw, {"Content-Encoding": "gzip"}, LIMIT)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < LIMIT + 8 * CHUNK, f"{peak / MIB:.1f} MiB held for a limit of {LIMIT / MIB:.0f} MiB"
