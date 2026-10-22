"""Answers as a server packs them, for the tests of the body reader: small ones to unpack, and one
that unpacks to far more than it weighs. Taken over from curriculum-extractor (tests/compressed.py).

Handed over in chunks, as the network does: httpx2 reads a response built from bytes as soon as it
is made, and unpacks it itself, so the reader under test would never see the packed bytes.
"""

import functools
import zlib
from collections.abc import AsyncIterator

MIB = 2**20
# What httpcore2 hands over per read from the network
CHUNK = 64 * 1024

_WBITS = {
    "gzip": 16 + zlib.MAX_WBITS,
    "x-gzip": 16 + zlib.MAX_WBITS,
    # "deflate" names a zlib stream; some servers send the bare deflate data
    "deflate": zlib.MAX_WBITS,
    "raw deflate": -zlib.MAX_WBITS,
}


def packed(data: bytes, encoding: str) -> bytes:
    """``data`` as a server sends it under ``encoding`` (or as it is, for "identity")."""
    if encoding == "identity":
        return data
    packer = zlib.compressobj(6, zlib.DEFLATED, _WBITS[encoding])
    return packer.compress(data) + packer.flush()


@functools.cache
def gzip_bomb(unpacked_mib: int = 400) -> bytes:
    """gzip of ``unpacked_mib`` MiB of zeros, about a thousandth of that on the wire; built once
    per run, as packing 400 MiB takes a couple of seconds."""
    packer = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
    block = bytes(MIB)
    return b"".join([packer.compress(block) for _ in range(unpacked_mib)] + [packer.flush()])


def in_chunks(data: bytes, size: int = CHUNK) -> list[bytes]:
    """``data`` in the pieces a transport would hand over."""
    return [data[start : start + size] for start in range(0, len(data), size)]


async def arriving(chunks: list[bytes]) -> AsyncIterator[bytes]:
    """``chunks`` as an async transport hands them over, one after another."""
    for chunk in chunks:
        yield chunk
