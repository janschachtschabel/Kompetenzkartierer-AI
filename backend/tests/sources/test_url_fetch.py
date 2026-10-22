"""Fetching a URL for the register without reaching inside the network (SSRF).

Hermetic: literals need no DNS, host names get a resolver of the test's, connections a recording
network backend, HTTP behaviour httpx2's MockTransport. The guards and the HTTP cases are taken over
from curriculum-extractor (tests/test_url_import.py); the pinning - the address checked is the one
connected to - is new here.
"""

import asyncio
import ssl
import tracemalloc
from collections.abc import Callable, Iterable
from typing import Any

import httpcore2
import httpx2
import pytest

from app.core.tracing import take_trace_headers
from app.sources.url_fetch import (
    BadAnswer,
    DownloadError,
    FileTooLarge,
    PinnedBackend,
    TooManyRedirects,
    UrlNotAllowed,
    check_url,
    fetch,
    filename_from_url,
    pinned_transport,
    public_address,
)
from tests.sources.compressed import CHUNK, MIB, arriving, gzip_bomb, in_chunks, packed

PUBLIC = "93.184.216.34"
PDF = b"%PDF-1.7 " + b"Lehrplan Physik " * 20_000


def answering(address: str) -> Callable[[str], list[str]]:
    return lambda host: [address]


# --- which URLs and addresses pass


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.org/x",
        "http:///no-host",
        "lehrplan.pdf",
        "javascript:alert(1)",
        "http://kka:geheim@example.org/lehrplan.pdf",  # a password the register would show
        "http://example.org/lehr plan.pdf",
        "http://example.org/lehrplan.pdf\n",
    ],
)
def test_only_http_with_a_host_and_nothing_hidden_is_fetched(url: str) -> None:
    with pytest.raises(UrlNotAllowed):
        check_url(url)


@pytest.mark.parametrize("sign", [0x202E, 0x200B], ids=["right-to-left-override", "zero-width-space"])
def test_a_url_with_a_format_sign_is_refused(sign: int) -> None:
    # the register shows the address as the title of an entry without one: it must show whole
    with pytest.raises(UrlNotAllowed):
        check_url(f"https://lehrplaene.example/Lehrplan{chr(sign)}fdp.exe")


def test_a_url_is_kept_with_its_scheme_in_small_letters() -> None:
    # the register holds http(s) only; "HTTPS://" is the same address
    assert check_url("HTTPS://Lehrplaene.example/A.pdf?x=1") == "https://Lehrplaene.example/A.pdf?x=1"


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.5",
        "192.168.1.1",
        "172.16.0.1",
        "169.254.169.254",  # the cloud's metadata address
        "100.64.0.1",  # carrier-grade NAT (RFC 6598): Kubernetes puts services there
        "::ffff:100.64.0.1",
        "224.0.0.1",  # multicast, which ipaddress calls global
        "239.255.255.250",
        "ff02::1",
        "64:ff9b::7f00:1",  # NAT64: 127.0.0.1 on the far side of the translator
        "fec0::1",  # site-local (deprecated by RFC 3879, still routed inside), which ipaddress calls global
    ],
)
def test_an_address_inside_any_network_is_refused(host: str) -> None:
    with pytest.raises(UrlNotAllowed):
        public_address(host, answering(PUBLIC))


@pytest.mark.parametrize("host", [PUBLIC, "2606:2800:220:1:248:1893:25c8:1946"])
def test_a_public_literal_passes_without_dns(host: str) -> None:
    def no_dns(name: str) -> list[str]:
        raise AssertionError("asked DNS for a literal")

    assert public_address(host, no_dns) == host


def test_a_host_name_passes_with_its_public_address() -> None:
    assert public_address("data.example.org", answering(PUBLIC)) == PUBLIC


def test_a_host_name_with_one_address_inside_is_refused() -> None:
    with pytest.raises(UrlNotAllowed):
        public_address("data.example.org", lambda host: [PUBLIC, "10.1.2.3"])


def test_the_refusal_names_no_address_and_reads_alike_for_internal_and_unknown_names() -> None:
    # naming the address, or answering an unknown name differently, told any account the inside
    def missing(host: str) -> list[str]:
        raise OSError("not found")

    def unencodable(host: str) -> list[str]:
        raise UnicodeError("label too long")

    with pytest.raises(UrlNotAllowed) as internal:
        public_address("intern.example", answering("10.1.2.3"))
    with pytest.raises(UrlNotAllowed) as unknown:
        public_address("nirgends.example", missing)
    with pytest.raises(UrlNotAllowed) as broken:
        public_address("xn--bcher-kva.example", unencodable)

    assert "10.1.2.3" not in str(internal.value)
    assert str(internal.value) == str(unknown.value) == str(broken.value)


# --- the address checked is the one connected to


class RecordingStream(httpcore2.AsyncMockStream):
    def __init__(self, buffer: list[bytes], record: dict[str, Any]) -> None:
        super().__init__(buffer)
        self.record = record
        record["sent"] = b""

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.record["sent"] += buffer

    async def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: str | None = None, timeout: float | None = None
    ) -> httpcore2.AsyncNetworkStream:
        self.record["tls_name"] = server_hostname
        return self


class RecordingBackend(httpcore2.AsyncNetworkBackend):
    """One answer per connection, in order; notes where each connection went."""

    def __init__(self, answers: Iterable[bytes]) -> None:
        self.answers = list(answers)
        self.connections: list[dict[str, Any]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore2.AsyncNetworkStream:
        record: dict[str, Any] = {"host": host, "port": port}
        self.connections.append(record)
        return RecordingStream([self.answers.pop(0)], record)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


def http_answer(status: str = "200 OK", body: bytes = b"%PDF-1.7", **headers: str) -> bytes:
    lines = [
        f"HTTP/1.1 {status}",
        f"Content-Length: {len(body)}",
        *(f"{k.replace('_', '-')}: {v}" for k, v in headers.items()),
    ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


@pytest.mark.anyio
async def test_the_connection_goes_to_the_address_that_was_checked() -> None:
    # DNS rebinding: a second lookup could answer with an inside address; there is only one
    lookups: list[str] = []

    def rebinding(host: str) -> list[str]:
        lookups.append(host)
        return [PUBLIC] if len(lookups) == 1 else ["127.0.0.1"]

    network = RecordingBackend([http_answer(Content_Type="application/pdf")])
    fetched = await fetch(
        "http://lehrplaene.example/lp.pdf",
        max_bytes=1000,
        transport=pinned_transport(PinnedBackend(rebinding, network)),
    )

    assert fetched.content == b"%PDF-1.7"
    assert lookups == ["lehrplaene.example"]
    assert [(c["host"], c["port"]) for c in network.connections] == [(PUBLIC, 80)]
    assert b"Host: lehrplaene.example" in network.connections[0]["sent"]


@pytest.mark.anyio
async def test_tls_checks_the_certificate_of_the_host_name_not_of_the_address() -> None:
    network = RecordingBackend([http_answer()])

    await fetch(
        "https://lehrplaene.example/lp.pdf",
        max_bytes=1000,
        transport=pinned_transport(PinnedBackend(answering(PUBLIC), network)),
    )

    assert network.connections[0]["host"] == PUBLIC
    assert network.connections[0]["tls_name"] == "lehrplaene.example"


@pytest.mark.anyio
async def test_a_host_inside_the_network_is_never_connected_to() -> None:
    network = RecordingBackend([http_answer()])

    with pytest.raises(UrlNotAllowed):
        await fetch(
            "http://intern.example/x",
            max_bytes=1000,
            transport=pinned_transport(PinnedBackend(answering("10.1.2.3"), network)),
        )

    assert network.connections == []


@pytest.mark.anyio
async def test_each_redirect_is_checked_where_it_connects() -> None:
    network = RecordingBackend([http_answer("302 Found", b"", Location="http://10.0.0.1/internal")])

    with pytest.raises(UrlNotAllowed):
        await fetch(
            f"http://{PUBLIC}/start",
            max_bytes=1000,
            transport=pinned_transport(PinnedBackend(answering(PUBLIC), network)),
        )

    assert [c["host"] for c in network.connections] == [PUBLIC]


# --- HTTP, through a mock transport


def mock(handler: Callable[[httpx2.Request], Any]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


@pytest.mark.anyio
async def test_a_fetch_returns_the_content_its_type_and_the_way_it_came() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/start":
            return httpx2.Response(302, headers={"location": "/lp.pdf"})
        return httpx2.Response(200, content=b"%PDF-1.7 body", headers={"content-type": "application/pdf"})

    fetched = await fetch(f"http://{PUBLIC}/start", max_bytes=1000, transport=mock(handler))

    assert fetched.content == b"%PDF-1.7 body"
    assert fetched.content_type == "application/pdf"
    assert fetched.chain == [f"http://{PUBLIC}/start", f"http://{PUBLIC}/lp.pdf"]


@pytest.mark.anyio
async def test_a_fetch_carries_the_trace_of_the_request_that_asked_for_it() -> None:
    asked: list[httpx2.Headers] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request.headers)
        return httpx2.Response(200, content=b"%PDF")

    take_trace_headers([(b"x-client-trace-id", b"trace-of-the-import")], "request-1")
    await fetch(f"http://{PUBLIC}/lp.pdf", max_bytes=1000, transport=mock(handler), user_agent="kka-test/1")

    assert asked[0]["x-client-trace-id"] == "trace-of-the-import"
    assert asked[0]["user-agent"] == "kka-test/1"


@pytest.mark.anyio
async def test_an_answer_over_the_limit_is_refused() -> None:
    # FileTooLarge: another attempt meets the same file
    with pytest.raises(FileTooLarge, match="size limit"):
        await fetch(
            f"http://{PUBLIC}/big",
            max_bytes=10,
            transport=mock(lambda request: httpx2.Response(200, content=b"0" * 100)),
        )


@pytest.mark.anyio
@pytest.mark.parametrize("status", [404, 403, 500])
async def test_an_error_status_is_a_download_error_naming_it(status: int) -> None:
    with pytest.raises(DownloadError) as failed:
        await fetch(
            f"http://{PUBLIC}/x", max_bytes=10, transport=mock(lambda request: httpx2.Response(status))
        )

    assert failed.value.status == status


@pytest.mark.anyio
async def test_a_transport_failure_is_reported_in_our_words() -> None:
    # "[Errno 111] Connection refused", a proxy, an address: the operator's, for the log
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("[Errno 111] Connection refused")

    with pytest.raises(DownloadError) as failed:
        await fetch(f"http://{PUBLIC}/lp.pdf", max_bytes=1000, transport=mock(handler))

    assert "Errno" not in str(failed.value) and "refused" not in str(failed.value)


@pytest.mark.anyio
async def test_the_log_names_only_the_scheme_and_host_of_a_failed_fetch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # a portal's download link may carry a token in its path, query or fragment
    url = f"https://{PUBLIC}/dl/SECRET-PATH?token=SECRET-QUERY#SECRET-FRAGMENT"

    def refusing(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    async def late(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200)

    caplog.set_level("INFO", logger="app.sources.url_fetch")
    with pytest.raises(DownloadError):
        await fetch(url, max_bytes=1000, transport=mock(refusing))
    with pytest.raises(DownloadError):
        await fetch(url, max_bytes=1000, transport=mock(late), total_timeout=0.1)

    assert len(caplog.records) == 2
    assert all(f"https://{PUBLIC}" in record.getMessage() for record in caplog.records)
    assert "SECRET" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("location", [f"http://{PUBLIC}:8o80/x", "mailto:a@b.test", "http://xn--zz.test/"])
async def test_a_redirect_to_an_address_that_cannot_be_spelled_is_a_download_error(location: str) -> None:
    with pytest.raises((DownloadError, UrlNotAllowed)):
        await fetch(
            f"http://{PUBLIC}/start",
            max_bytes=1000,
            transport=mock(lambda request: httpx2.Response(302, headers={"location": location})),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "location",
    [f"http://{PUBLIC}:8o80/x".encode(), f"http://a{chr(0x200D)}b.example/x".encode()],
    ids=["port-of-letters", "host-idna-refuses"],
)
async def test_a_redirect_to_an_address_that_cannot_be_read_is_a_bad_answer(location: bytes) -> None:
    # a port of letters, a host IDNA refuses (sent as a server sends it, in bytes): the same again
    with pytest.raises(BadAnswer, match="cannot be read"):
        await fetch(
            f"http://{PUBLIC}/start",
            max_bytes=1000,
            transport=mock(lambda request: httpx2.Response(302, headers={b"location": location})),
        )


@pytest.mark.anyio
@pytest.mark.parametrize("status", [302, 304])
async def test_a_redirect_without_an_address_is_a_bad_answer(status: int) -> None:
    # httpx2 calls every 3xx a redirect, 304 too
    with pytest.raises(BadAnswer, match="without an address"):
        await fetch(
            f"http://{PUBLIC}/x", max_bytes=1000, transport=mock(lambda request: httpx2.Response(status))
        )


@pytest.mark.anyio
async def test_too_many_redirects_end_the_fetch() -> None:
    with pytest.raises(TooManyRedirects, match="redirects"):
        await fetch(
            f"http://{PUBLIC}/loop",
            max_bytes=1000,
            transport=mock(lambda request: httpx2.Response(302, headers={"location": "/loop"})),
        )


@pytest.mark.anyio
async def test_a_fetch_gives_up_after_its_total_time() -> None:
    # per-phase timeouts only: a server sending a byte every 29 s held the fetch as long as it liked
    async def handler(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200, content=b"late")

    with pytest.raises(DownloadError, match="too long"):
        await fetch(f"http://{PUBLIC}/slow", max_bytes=1000, transport=mock(handler), total_timeout=0.1)


@pytest.mark.anyio
async def test_a_fetch_unpacking_far_past_its_limit_is_stopped_holding_no_more_than_the_limit() -> None:
    raw = in_chunks(gzip_bomb())
    limit = 4 * MIB

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=arriving(raw), headers={"Content-Encoding": "gzip"})

    tracemalloc.start()
    try:
        with pytest.raises(DownloadError, match="size limit"):
            await fetch(f"http://{PUBLIC}/lp.pdf", max_bytes=limit, transport=mock(handler))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak < limit + 8 * CHUNK


@pytest.mark.anyio
@pytest.mark.parametrize("encoding", ["gzip", "x-gzip", "deflate"])
async def test_a_fetch_packed_as_asked_is_unpacked(encoding: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        wire = in_chunks(packed(PDF, encoding), 1_000)
        return httpx2.Response(200, content=arriving(wire), headers={"Content-Encoding": encoding})

    assert (
        await fetch(f"http://{PUBLIC}/lp.pdf", max_bytes=len(PDF), transport=mock(handler))
    ).content == PDF


@pytest.mark.anyio
async def test_a_fetch_whose_compressed_body_breaks_off_is_tried_again() -> None:
    # a transfer cut short: another attempt may get the whole; none is kept as the file
    wire = packed(PDF, "gzip")
    cut = wire[: len(wire) // 2]

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=arriving([cut]), headers={"Content-Encoding": "gzip"})

    with pytest.raises(DownloadError) as failed:
        await fetch(f"http://{PUBLIC}/lp.pdf", max_bytes=len(PDF), transport=mock(handler))

    assert not isinstance(failed.value, (FileTooLarge, TooManyRedirects, BadAnswer))


@pytest.mark.anyio
@pytest.mark.parametrize("encoding", ["gzip, gzip", "br", "zstd"])
async def test_a_fetch_packed_twice_or_in_an_unknown_way_is_refused(encoding: str) -> None:
    asked: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request.headers.get("Accept-Encoding"))
        wire = [packed(packed(PDF, "gzip"), "gzip")]
        return httpx2.Response(200, content=arriving(wire), headers={"Content-Encoding": encoding})

    with pytest.raises(BadAnswer, match="encoding"):
        await fetch(f"http://{PUBLIC}/lp.pdf", max_bytes=len(PDF), transport=mock(handler))

    assert asked == ["gzip, deflate"]  # asked for only what the reader unpacks


# --- the document's name, from its address


def test_a_file_name_in_the_query_string_is_used() -> None:
    # portals serve a PDF from an opaque path and put the real name in a parameter
    url = "https://www.schulportal-thueringen.de/tip/resources/medien/14629?dateiname=Physik_RS_Nov_2012_7_10.pdf"

    assert filename_from_url(url) == "Physik_RS_Nov_2012_7_10.pdf"


def test_the_path_wins_when_it_names_a_file() -> None:
    assert filename_from_url("https://x.de/lehrplan.pdf?v=2") == "lehrplan.pdf"
