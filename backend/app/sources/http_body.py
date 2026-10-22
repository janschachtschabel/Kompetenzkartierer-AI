"""Reading an HTTP answer no further than a limit, counted after unpacking.

A source that sends more than it ever would must not fill a worker: the body is counted after
decompression, so an answer that unpacks to far more than it weighs is stopped at the limit too.
Unpacked here rather than by httpx2, which inflates each chunk it receives in one piece: 822
bytes of gzip became 840 MiB before the limit was looked at (the old app's audit, G-01). Read
raw and unpacked a piece at a time, reading never holds more than the limit and a chunk. One
layer of gzip or deflate is unpacked - all a client of ours asks for (ACCEPT_ENCODING) -, anything
else refused. Taken over from curriculum-extractor (services/http_body.py), async only.
"""

import zlib

import httpx2

# What every client of ours sends as Accept-Encoding: what LimitedBody unpacks
ACCEPT_ENCODING = "gzip, deflate"
# The most one call to zlib may return; unasked, it returns all it can make of its input at once
_PIECE = 64 * 1024
_GZIP = 16 + zlib.MAX_WBITS
_WBITS = {"gzip": _GZIP, "x-gzip": _GZIP, "deflate": zlib.MAX_WBITS}


class BodyTooLarge(Exception):
    """The answer went past the limit."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"more than {limit:,} bytes")
        self.limit = limit


class UnsupportedEncoding(Exception):
    """The answer is packed in more than one layer, or in a format this reader does not know."""

    def __init__(self, encoding: str) -> None:
        # cut short: the value is the server's, and the message reaches the person who asked
        super().__init__(f"an unsupported content encoding: {encoding[:40]!r}")
        self.encoding = encoding


class LimitedBody:
    """One answer's body, fed its raw chunks and unpacked within ``limit`` bytes.

    Raises UnsupportedEncoding when made, BodyTooLarge as soon as the unpacked bytes pass the
    limit, and httpx2.DecodingError for a broken compressed stream.
    """

    def __init__(self, content_encoding: str | None, limit: int) -> None:
        encoding = (content_encoding or "").strip().lower()
        # stacked encodings are comma-separated; so are two header lines, which httpx2 joins
        if "," in encoding or encoding not in ("", "identity", *_WBITS):
            raise UnsupportedEncoding(encoding)
        self._inflater = zlib.decompressobj(_WBITS[encoding]) if encoding in _WBITS else None
        # "deflate" names a zlib stream, and some servers send the bare deflate data instead;
        # its first bytes tell which, as in httpx
        self._may_be_bare = encoding == "deflate"
        self._limit = limit
        self._size = 0
        self._pieces: list[bytes] = []

    def feed(self, chunk: bytes) -> None:
        """Take the next raw chunk of the body."""
        if not chunk:
            return
        if self._inflater is None:
            self._keep(chunk)
            return
        if self._inflater.eof:
            # what follows the end of the stream is dropped, but counted: a server could go on
            # sending it for ever
            self._count(len(chunk))
            return
        data = chunk
        while not self._inflater.eof:
            wanted = min(_PIECE, self._limit - self._size + 1)  # a byte past the limit tells
            piece = self._inflate(data, wanted)
            self._keep(piece)
            # short of what was wanted, zlib has used up its input; a full piece may leave output
            if len(piece) < wanted:
                return
            data = self._inflater.unconsumed_tail

    def feed_unpacked(self, content: bytes) -> None:
        """Take a body httpx2 has read and unpacked already (a response built from bytes, as a
        test's transport builds one): counted, not unpacked again."""
        self._keep(content)

    def result(self) -> bytes:
        return b"".join(self._pieces)

    def _inflate(self, data: bytes, wanted: int) -> bytes:
        assert self._inflater is not None  # noqa: S101 - only a compressed body is inflated
        try:
            piece = self._inflater.decompress(data, wanted)
        except zlib.error as error:
            if not self._may_be_bare:
                raise httpx2.DecodingError(str(error)) from error
            self._may_be_bare = False
            self._inflater = zlib.decompressobj(-zlib.MAX_WBITS)
            return self._inflate(data, wanted)
        self._may_be_bare = False
        return piece

    def _keep(self, piece: bytes) -> None:
        self._count(len(piece))
        if piece:
            self._pieces.append(piece)

    def _count(self, size: int) -> None:
        self._size += size
        if self._size > self._limit:
            raise BodyTooLarge(self._limit)


async def aread_body(response: httpx2.Response, limit: int) -> bytes:
    """The body of a streamed ``response``, or BodyTooLarge past ``limit`` unpacked bytes."""
    body = LimitedBody(response.headers.get("content-encoding"), limit)
    if response.is_stream_consumed:
        body.feed_unpacked(response.content)
    else:
        async for chunk in response.aiter_raw():
            body.feed(chunk)
    return body.result()
