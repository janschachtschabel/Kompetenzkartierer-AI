"""One look at an address for the check job (plan M1, 2.5): the answer's status, type, size,
SHA-256 and date, its body streamed and hashed, never kept. The network is httpx2's MockTransport;
the guards on the way (public hosts, redirects checked where they connect) are fetch's own
(tests/sources/test_url_fetch.py)."""

import asyncio
import hashlib
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from app.sources.url_fetch import BadAnswer, DownloadError, TooManyRedirects
from app.sources.url_probe import probe
from tests.sources.compressed import arriving, in_chunks, packed

pytestmark = pytest.mark.anyio

URL = "https://lehrplaene.example/medien/14629?dateiname=Physik.pdf"
PDF = b"%PDF-1.7 " + b"Lehrplan " * 5_000
DOCX = b"PK\x03\x04" + b"\x00" * 200
RTF = b"{\\rtf1\\ansi Lehrplan}"


def mock(handler: Callable[[httpx2.Request], Any]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


def answer(
    status: int = 200, body: bytes | list[bytes] = PDF, headers: dict[str, str] | None = None
) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        content = body if isinstance(body, bytes) else arriving(body)
        return httpx2.Response(status, content=content, headers=headers)

    return mock(handler)


async def test_a_probe_hashes_what_it_streams_and_says_what_the_server_said() -> None:
    headers = {"content-type": "application/pdf", "last-modified": "Wed, 01 Jul 2026 08:00:00 GMT"}

    found = await probe(
        URL, max_bytes=1_000_000, transport=answer(body=in_chunks(PDF, 4_096), headers=headers)
    )

    assert (found.status_code, found.size, found.sha256) == (200, len(PDF), hashlib.sha256(PDF).digest())
    assert (found.kind, found.too_large, found.chain) == ("pdf", False, [URL])
    assert (found.content_type, found.last_modified) == ("application/pdf", "Wed, 01 Jul 2026 08:00:00 GMT")


async def test_a_packed_body_is_hashed_as_the_file_it_unpacks_to() -> None:
    # as source.fetch stores it: the SHA-256 of the check names the same file
    wire = in_chunks(packed(PDF, "gzip"), 1_000)

    found = await probe(
        URL, max_bytes=1_000_000, transport=answer(body=wire, headers={"content-encoding": "gzip"})
    )

    assert (found.size, found.sha256) == (len(PDF), hashlib.sha256(PDF).digest())


async def test_a_body_past_the_limit_is_too_large_and_still_known_by_its_first_bytes() -> None:
    found = await probe(URL, max_bytes=1_000, transport=answer(body=in_chunks(PDF, 512)))

    assert (found.status_code, found.too_large, found.kind) == (200, True, "pdf")
    assert (found.size, found.sha256) == (None, None)


@pytest.mark.parametrize("status", [404, 403, 410, 429, 500, 503])
async def test_an_answer_that_refuses_is_its_status_and_no_body_is_read(status: int) -> None:
    found = await probe(URL, max_bytes=1_000, transport=answer(status, body=b"<html>Forbidden</html>"))

    assert found.status_code == status
    assert (found.size, found.sha256, found.kind, found.too_large) == (None, None, None, False)


async def test_redirects_are_followed_and_the_way_kept() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/start":
            return httpx2.Response(301, headers={"location": "/lp.pdf"})
        return httpx2.Response(200, content=PDF)

    found = await probe("https://lehrplaene.example/start", max_bytes=1_000_000, transport=mock(handler))

    assert found.chain == ["https://lehrplaene.example/start", "https://lehrplaene.example/lp.pdf"]
    assert (found.status_code, found.kind) == (200, "pdf")


async def test_a_redirect_loop_is_too_many_redirects() -> None:
    loop = mock(lambda request: httpx2.Response(302, headers={"location": "/again"}))

    with pytest.raises(TooManyRedirects):
        await probe(URL, max_bytes=1_000, transport=loop)


@pytest.mark.parametrize(
    ("body", "headers", "kind"),
    [
        (DOCX, {}, "docx"),
        (RTF, {}, "rtf"),
        (b"<p>Lehrplan</p>", {"content-type": "text/html; charset=utf-8"}, "html"),
        (b"<p>Lehrplan</p>", {"content-type": "application/xhtml+xml"}, "html"),
        (
            b"\xef\xbb\xbf\n  <!DOCTYPE html><html></html>",
            {"content-type": "application/octet-stream"},
            "html",
        ),
        (b"<HTML><body>Plan</body></HTML>", {}, "html"),
        (b"Lehrplan als Text", {"content-type": "text/plain"}, "other"),
        (b"", {}, "other"),
    ],
)
async def test_the_kind_is_told_by_the_first_bytes_and_the_server_s_type(
    body: bytes, headers: dict[str, str], kind: str
) -> None:
    found = await probe(URL, max_bytes=1_000_000, transport=answer(body=body, headers=headers))

    assert found.kind == kind


async def test_the_probe_sends_its_user_agent() -> None:
    asked: list[httpx2.Headers] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request.headers)
        return httpx2.Response(200, content=PDF)

    await probe(URL, max_bytes=1_000_000, transport=mock(handler), user_agent="kka-check/1")

    assert asked[0]["user-agent"] == "kka-check/1"


async def test_no_answer_in_time_is_a_download_error() -> None:
    async def late(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200, content=PDF)

    with pytest.raises(DownloadError, match="too long"):
        await probe(URL, max_bytes=1_000, transport=mock(late), total_timeout=0.1)


async def test_a_body_that_cannot_be_unpacked_is_a_bad_answer() -> None:
    broken = answer(body=[b"\x1f\x8b\x08\x00not gzip at all"], headers={"content-encoding": "gzip"})

    with pytest.raises(BadAnswer):
        await probe(URL, max_bytes=1_000, transport=broken)


async def test_a_long_header_is_cut_to_what_the_register_holds() -> None:
    found = await probe(
        URL,
        max_bytes=1_000_000,
        transport=answer(
            headers={"content-type": "application/pdf; " + "x" * 300, "last-modified": "y" * 300}
        ),
    )

    assert found.content_type is not None and len(found.content_type) == 200
    assert found.last_modified is not None and len(found.last_modified) == 100
