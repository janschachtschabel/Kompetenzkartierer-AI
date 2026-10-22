"""One look at an address for the check job (plan M1, 2.5): what the server answers, the body
streamed and hashed, never kept.

The way there is fetch's (app/sources/url_fetch.follow): public hosts only, each redirect checked
where it connects, one deadline, no proxy. An answer that is no 2xx is its status, its body
unread. A body is unpacked as source.fetch unpacks it and hashed as it arrives, so its SHA-256
names the file a fetch would store; past ``max_bytes`` the probe stops reading, and the answer is
too large, known by its first bytes. What it is: a PDF, DOCX or RTF by its signature (as
app/sources/filetype.py reads one), HTML by the server's type or its first tag, else other.
"""

import hashlib
from dataclasses import dataclass, replace

import httpx2

from app.core.auth import visible_only
from app.sources.filetype import DOCX_MIME, detect_type
from app.sources.http_body import BodyTooLarge, BrokenCompression, UnsupportedEncoding, aread_body
from app.sources.register import DetectedKind
from app.sources.url_fetch import MAX_REDIRECTS, PHASE_TIMEOUT_S, TOTAL_TIMEOUT_S, BadAnswer, follow

HEAD_BYTES = 1024  # what the kind is told by
# What url_check holds of the server's headers
CONTENT_TYPE_SIGNS = 200
LAST_MODIFIED_SIGNS = 100
_KIND_OF_TYPE: dict[str, DetectedKind] = {
    "application/pdf": "pdf",
    DOCX_MIME: "docx",
    "application/rtf": "rtf",
}
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_HTML_STARTS = (b"<!doctype html", b"<html")


@dataclass(frozen=True)
class Probe:
    status_code: int  # of the answer that was no redirect
    chain: list[str]  # every address asked, redirects in order
    content_type: str | None
    last_modified: str | None
    kind: DetectedKind | None  # of an answer of 2xx
    too_large: bool  # a body of 2xx past the limit: no size, no hash
    size: int | None  # of a body read to its end
    sha256: bytes | None


async def probe(
    url: str,
    *,
    max_bytes: int,
    transport: httpx2.AsyncBaseTransport | None = None,
    user_agent: str = "Kompetenzkartierer-AI",
    timeout: float = PHASE_TIMEOUT_S,
    total_timeout: float = TOTAL_TIMEOUT_S,
    max_redirects: int = MAX_REDIRECTS,
) -> Probe:
    """What ``url`` answers; UrlNotAllowed for an address that is not public, DownloadError for no
    answer (or none in time), TooManyRedirects, BadAnswer for a redirect or body no attempt can use."""

    async def read(response: httpx2.Response) -> Probe:
        return await _look(response, max_bytes)

    found, chain = await follow(
        url,
        read,
        transport=transport,
        user_agent=user_agent,
        timeout=timeout,
        total_timeout=total_timeout,
        max_redirects=max_redirects,
    )
    return replace(found, chain=chain)


async def _look(response: httpx2.Response, max_bytes: int) -> Probe:
    content_type = _header(response, "content-type", CONTENT_TYPE_SIGNS)
    last_modified = _header(response, "last-modified", LAST_MODIFIED_SIGNS)
    answered = Probe(response.status_code, [], content_type, last_modified, None, False, None, None)
    if not 200 <= response.status_code < 300:
        return answered
    digest = hashlib.sha256()
    head = bytearray()
    sizes: list[int] = []

    def take(piece: bytes) -> None:
        digest.update(piece)
        sizes.append(len(piece))
        if len(head) < HEAD_BYTES:
            head.extend(piece[: HEAD_BYTES - len(head)])

    try:
        await aread_body(response, max_bytes, take)
    except BodyTooLarge:
        return replace(answered, kind=_kind(bytes(head), content_type), too_large=True)
    except UnsupportedEncoding as error:
        raise BadAnswer(str(error)) from None
    except BrokenCompression:
        raise BadAnswer("the compressed answer cannot be unpacked") from None
    return replace(answered, kind=_kind(bytes(head), content_type), size=sum(sizes), sha256=digest.digest())


def _header(response: httpx2.Response, name: str, limit: int) -> str | None:
    value = response.headers.get(name)
    if value is None:
        return None
    return " ".join(visible_only(value).split())[:limit] or None


def _kind(head: bytes, content_type: str | None) -> DetectedKind:
    detected = detect_type(None, head)  # no name: the signatures only
    if detected is not None and detected.mime in _KIND_OF_TYPE:
        return _KIND_OF_TYPE[detected.mime]
    media = (content_type or "").split(";")[0].strip().lower()
    if media in _HTML_TYPES or head.lstrip(b"\xef\xbb\xbf \t\r\n").lower().startswith(_HTML_STARTS):
        return "html"
    return "other"
