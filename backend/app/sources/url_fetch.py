"""Fetching a URL for the register without reaching inside the network (SSRF).

Only http(s), and only hosts whose every address is public. The address checked is the one
connected to: PinnedBackend resolves the host once, checks every address and connects to the
first, so no second lookup can answer with an inside address (DNS rebinding). TLS still checks
the certificate against the host name - httpcore2 hands the URL's host to the TLS handshake, not
the address. Redirects are followed by hand, each through the same connection check; the body is
read within the limit after unpacking (app/sources/http_body.py); one deadline holds the whole
fetch; no proxy from the environment. Taken over from curriculum-extractor (url_import.py), which
left the rebinding open; the pinning is new.
"""

import asyncio
import ipaddress
import logging
import socket
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpcore2
import httpx2

from app.core.tracing import outgoing_headers
from app.sources.http_body import ACCEPT_ENCODING, BodyTooLarge, UnsupportedEncoding, aread_body

log = logging.getLogger(__name__)

PHASE_TIMEOUT_S = 30.0
# The whole fetch, redirects included: per phase alone, a server sending a byte every 29 s held
# a fetch for as long as it liked
TOTAL_TIMEOUT_S = 120.0
MAX_REDIRECTS = 3
# One answer for every host that is not publicly reachable: naming what an internal name resolved
# to - or answering an unknown name differently - told any account the inside of the network
NOT_PUBLIC = "the host is not publicly reachable"

ResolveHost = Callable[[str], list[str]]


class UrlNotAllowed(ValueError):
    """The URL is no http(s) address of a public host."""


class DownloadError(ValueError):
    """The fetch failed, in our words; what the transport said is the operator's, in the log.
    ``status`` is the HTTP status of an answer that refused, if one did. Another attempt may
    fare better, unless the error is one of the kinds below."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class FileTooLarge(DownloadError):
    """The file passed the limit: another attempt meets the same file."""


class TooManyRedirects(DownloadError):
    """The redirects went on past the limit."""


class BadAnswer(DownloadError):
    """An answer no attempt can use: a redirect without an address or to one that cannot be
    read, a body packed in a way not unpacked here."""


@dataclass(frozen=True)
class Fetched:
    content: bytes
    content_type: str
    chain: list[str]  # every address asked, redirects in order


def default_resolver(host: str) -> list[str]:
    return [str(info[4][0]) for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


def is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """An address the wider internet routes to. ``is_global`` comes from IANA's registry of
    special-purpose ranges (it knows 100.64.0.0/10, where Kubernetes puts services); it does not
    exclude the NAT64 prefix (64:ff9b::7f00:1 is 127.0.0.1 beyond the translator), multicast, nor
    the site-local fec0::/10, deprecated (RFC 3879) but still routed inside some networks."""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return is_public(address.ipv4_mapped)
        if address.is_site_local:
            return False
    return address.is_global and not (address.is_reserved or address.is_multicast)


def check_url(url: str) -> str:
    """``url`` with its scheme in small letters, or UrlNotAllowed unless it is http(s) with a host,
    without a user or password (the register would show them) and without spaces or control
    signs."""
    if any(sign.isspace() or unicodedata.category(sign) == "Cc" for sign in url):
        raise UrlNotAllowed("the address holds spaces or control signs")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UrlNotAllowed(f"only http and https addresses are fetched, not {parts.scheme[:20] or 'none'!r}")
    if not parts.hostname:
        raise UrlNotAllowed("the address names no host")
    if "@" in parts.netloc:
        raise UrlNotAllowed("the address must not hold a user or a password")
    return parts.geturl()


def public_address(host: str, resolve: ResolveHost) -> str:
    """The address to connect to for ``host``: the literal itself, or the first the resolver gives;
    UrlNotAllowed unless every address is public. Blocks on DNS: callers run it in a thread."""
    try:
        addresses = [str(ipaddress.ip_address(host))]  # a literal asks no DNS
    except ValueError:
        try:
            addresses = resolve(host)
        except (OSError, UnicodeError) as error:  # UnicodeError: an IDN label it cannot encode
            log.info("the host %s did not resolve: %s", host, error)
            raise UrlNotAllowed(NOT_PUBLIC) from None
    if not addresses:
        raise UrlNotAllowed(NOT_PUBLIC)
    for address in addresses:
        if not is_public(ipaddress.ip_address(address)):
            log.info("the host %s resolves to the non-public address %s", host, address)
            raise UrlNotAllowed(NOT_PUBLIC)
    return addresses[0]


class PinnedBackend(httpcore2.AsyncNetworkBackend):
    """Connects to the address checked for the host, and to no other."""

    def __init__(
        self, resolve: ResolveHost = default_resolver, inner: httpcore2.AsyncNetworkBackend | None = None
    ):
        self._resolve = resolve
        self._inner = inner or httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        address = await asyncio.to_thread(public_address, host, self._resolve)
        return await self._inner.connect_tcp(
            address, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[Any] | None = None
    ) -> httpcore2.AsyncNetworkStream:
        raise UrlNotAllowed("no local socket is fetched")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _PinnedTransport(httpx2.AsyncHTTPTransport):
    """httpx2's transport over a PinnedBackend. It hands no network backend to its connection
    pool, so the pool is made again with one; trust_env=False: no proxy, no certificate path of
    the environment."""

    def __init__(self, backend: httpcore2.AsyncNetworkBackend) -> None:
        super().__init__(trust_env=False)
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=httpcore2.default_ssl_context(), network_backend=backend, http1=True, http2=False
        )


def pinned_transport(backend: httpcore2.AsyncNetworkBackend | None = None) -> httpx2.AsyncBaseTransport:
    return _PinnedTransport(backend or PinnedBackend())


async def fetch(
    url: str,
    *,
    max_bytes: int,
    transport: httpx2.AsyncBaseTransport | None = None,
    user_agent: str = "Kompetenzkartierer-AI",
    timeout: float = PHASE_TIMEOUT_S,
    total_timeout: float = TOTAL_TIMEOUT_S,
    max_redirects: int = MAX_REDIRECTS,
) -> Fetched:
    """Fetch ``url``; UrlNotAllowed for an address that is not public, DownloadError for a fetch
    that failed - FileTooLarge past ``max_bytes``, TooManyRedirects past ``max_redirects``,
    BadAnswer for an answer no attempt can use. The request carries the trace of the one being
    served."""
    chain: list[str] = []
    current = url
    headers = {**outgoing_headers(), "Accept-Encoding": ACCEPT_ENCODING, "User-Agent": user_agent}
    try:
        async with (
            asyncio.timeout(total_timeout),
            httpx2.AsyncClient(
                transport=transport or pinned_transport(),
                follow_redirects=False,
                timeout=timeout,
                trust_env=False,
                event_hooks={"response": [_stop_at_redirect]},
            ) as client,
        ):
            for _ in range(max_redirects + 1):
                check_url(current)
                chain.append(current)
                try:
                    async with client.stream("GET", current, headers=headers) as response:
                        content = await _body(response, max_bytes)
                        return Fetched(content, response.headers.get("content-type", ""), chain)
                except _Redirect as redirect:
                    current = _redirect_target(current, redirect.location)
    except TimeoutError:
        log.warning("the fetch of %s ran past %.0f s", _site(current), total_timeout)
        raise DownloadError("the fetch took too long") from None
    # InvalidURL is no HTTPError: the entry's own address may hold a port of letters; nor is
    # idna's IDNAError, a UnicodeError, which a broken xn-- label raises
    except (httpx2.HTTPError, httpx2.InvalidURL, UnicodeError) as error:
        log.warning("the fetch of %s failed: %s", _site(current), error)
        raise DownloadError("the server could not be reached, or the transfer broke off") from None
    raise TooManyRedirects("too many redirects")


def _site(url: str) -> str:
    """Scheme and host of ``url``, for the log: a download link may carry a token anywhere else."""
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.hostname or ''}"
    except ValueError:  # brackets that close no IPv6 address
        return "an address that cannot be read"


class _Redirect(Exception):
    """An answer of 3xx, stopped before httpx2 reads its Location: httpx2 builds a request of its
    own from it even when it does not follow, and an address it cannot read became a
    RemoteProtocolError, as a broken connection does, or a bare ValueError."""

    def __init__(self, location: str | None) -> None:
        super().__init__(location)
        self.location = location


async def _stop_at_redirect(response: httpx2.Response) -> None:
    if response.is_redirect:  # every 3xx, 304 too
        raise _Redirect(response.headers.get("location"))


def _redirect_target(current: str, location: str | None) -> str:
    if not location:
        raise BadAnswer("a redirect without an address")
    try:
        return str(httpx2.URL(current).join(location))
    except httpx2.InvalidURL:
        raise BadAnswer("a redirect to an address that cannot be read") from None


async def _body(response: httpx2.Response, max_bytes: int) -> bytes:
    if response.status_code >= 400:
        raise DownloadError(f"the server answered {response.status_code}", response.status_code)
    try:
        return await aread_body(response, max_bytes)
    except BodyTooLarge:
        raise FileTooLarge("the file exceeds the size limit") from None
    except UnsupportedEncoding as error:
        raise BadAnswer(str(error)) from None


def filename_from_url(url: str) -> str | None:
    """The document's name: the path's, if it names a file, else the first query value that does
    (portals serve a PDF from ``/medien/14629?dateiname=Physik.pdf``)."""
    parts = urlsplit(url)
    name = PurePosixPath(unquote(parts.path)).name
    if _looks_like_a_file(name):
        return name
    for values in parse_qs(parts.query).values():
        for value in values:
            candidate = PurePosixPath(unquote(value)).name
            if _looks_like_a_file(candidate):
                return candidate
    return name or None


def _looks_like_a_file(name: str) -> bool:
    """A name with an ending; a bare id like "14629" is none."""
    return bool(name) and "." in name.strip(".")
