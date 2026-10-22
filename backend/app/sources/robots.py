"""What a host's robots.txt allows the check job (RFC 9309; plan M1, 2.5).

urllib.robotparser takes the first rule that matches; RFC 9309 the longest, an allow winning a
tie: after "Allow: /", "Disallow: /intern" says no to /intern/lp.pdf, which robotparser allows.
So the rules are read here: the groups naming our product token (case-insensitive, combined),
else those of "*"; patterns with * for any run of signs and a closing $ for the end; rule and
address compared alike - signs beyond ASCII percent-encoded, the escape of an unreserved sign
decoded (RFC 9309 2.2.2), every other escape in capitals. A line is split at its first colon:
no pattern backtracks over a line of space. A group with more rules, or longer ones, than the
matching holds forbids everything: what is not read is not taken to allow.

Fetched once per origin the way fetch goes (url_fetch.follow), five redirects deep, with no trace
of ours: 2xx gives the rules of the first 500 KiB, a line the cut went through counting for
nothing; 4xx says there are none (the file is unavailable, RFC 9309 2.3.1.3), as does a file not
found within five redirects or behind a redirect that cannot be read. 429, 5xx, no answer, a
file that cannot be unpacked, or a redirect to where no request may go leave the host for a
later check (HostDeferred) - RFC 9309 has a crawler assume complete disallow then. A host that
is not to be asked at all is refused as such (url_fetch.HostRefused).
"""

import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import httpx2

from app.sources.http_body import BodyTooLarge, BrokenCompression, UnsupportedEncoding, aread_body
from app.sources.url_fetch import (
    PHASE_TIMEOUT_S,
    TOTAL_TIMEOUT_S,
    BadAnswer,
    DownloadError,
    HostRefused,
    TooManyRedirects,
    UrlNotAllowed,
    follow,
)

ROBOTS_BYTES = 500 * 1024  # what a crawler must read at least (RFC 9309 2.5)
ROBOTS_REDIRECTS = 5  # what it must follow at least (2.3.1.2)
# What the matching of every address against every rule holds: 2000 rules of 2000 signs against
# the longest address of the seed take well under a second
MAX_RULES = 2000
MAX_RULE_SIGNS = 2000
_KEY = re.compile(r"[A-Za-z-]+")
_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
# Every sign of ASCII but the space and controls stands as it is; anything else is percent-encoded
_AS_IT_IS = "".join(chr(code) for code in range(0x21, 0x7F))
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_BYTE_ORDER_MARK = chr(0xFEFF)


class HostDeferred(Exception):
    """The host's robots.txt could not be had now (``status`` 429 or 5xx, or none: no answer, or
    none that could be read)."""

    def __init__(self, status: int | None) -> None:
        super().__init__(f"robots.txt not to be had now ({status or 'no answer'})")
        self.status = status


@dataclass(frozen=True)
class Rules:
    """The rules of robots.txt that count for us; none allow everything."""

    allow: tuple[str, ...] = ()
    disallow: tuple[str, ...] = ()

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        target = _spelled(parts.path or "/") + (f"?{_spelled(parts.query)}" if parts.query else "")
        if target == "/robots.txt":
            return True
        allowed = max((len(rule) for rule in self.allow if _matches(rule, target)), default=-1)
        denied = max((len(rule) for rule in self.disallow if _matches(rule, target)), default=-1)
        return allowed >= denied


EVERYTHING_FORBIDDEN = Rules(disallow=("/",))


class _Enough(Exception):
    """The first 500 KiB are in: what follows is no part of the rules."""


def product_token(user_agent: str) -> str:
    """The name a robots.txt knows us by: the user agent's first word, without its version."""
    return user_agent.split()[0].split("/")[0] if user_agent.split() else user_agent


def parse_robots(text: str, product: str) -> Rules:
    ours: tuple[list[str], list[str]] = ([], [])
    everyone: tuple[list[str], list[str]] = ([], [])
    named_us = False
    agents: list[str] = []
    in_rules = False  # the group's rules have begun: the next user-agent starts a group
    for raw in text.lstrip(_BYTE_ORDER_MARK).splitlines():
        key, colon, value = raw.split("#", 1)[0].partition(":")
        key = key.strip()
        if not colon or not _KEY.fullmatch(key):
            continue
        key, value = key.lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agent = product_token(value).lower()
            agents.append(agent)
            named_us = named_us or agent == product.lower()
        elif key in ("allow", "disallow"):
            in_rules = True
            if not value or not agents:  # an empty rule says nothing; one of no group counts for none
                continue
            rule = _spelled(value)
            index = 0 if key == "allow" else 1
            if product.lower() in agents:
                ours[index].append(rule)
            if "*" in agents:
                everyone[index].append(rule)
    allow, disallow = ours if named_us else everyone
    rules = (*allow, *disallow)
    if len(rules) > MAX_RULES or any(len(rule) > MAX_RULE_SIGNS for rule in rules):
        return EVERYTHING_FORBIDDEN
    return Rules(tuple(allow), tuple(disallow))


async def read_robots(
    origin: str,
    product: str,
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    user_agent: str = "Kompetenzkartierer-AI",
    timeout: float = PHASE_TIMEOUT_S,
    total_timeout: float = TOTAL_TIMEOUT_S,
) -> Rules:
    """The rules of ``origin``'s robots.txt for ``product``; HostDeferred when it cannot be had
    now, HostRefused (a UrlNotAllowed) for a host of the origin's that is not to be asked."""

    async def read(response: httpx2.Response) -> tuple[int, bytes]:
        if not 200 <= response.status_code < 300:
            return response.status_code, b""
        kept = bytearray()

        def take(piece: bytes) -> None:
            room = ROBOTS_BYTES - len(kept)
            kept.extend(piece[:room])
            if len(piece) > room:
                raise _Enough

        try:
            await aread_body(response, 2 * ROBOTS_BYTES, take)
        except (_Enough, BodyTooLarge):
            # cut at 500 KiB: the line the cut went through counts for nothing
            return response.status_code, bytes(kept[: kept.rfind(b"\n") + 1])
        return response.status_code, bytes(kept)

    try:
        (status, body), _ = await follow(
            f"{origin}/robots.txt",
            read,
            transport=transport,
            user_agent=user_agent,
            timeout=timeout,
            total_timeout=total_timeout,
            max_redirects=ROBOTS_REDIRECTS,
            trace=False,
        )
    except (TooManyRedirects, BadAnswer):
        return Rules()  # not found within five redirects, or behind one that cannot be read
    except (UnsupportedEncoding, BrokenCompression):
        raise HostDeferred(None) from None  # there, with rules we cannot read
    except UrlNotAllowed as error:
        if isinstance(error, HostRefused) and error.host == httpx2.URL(origin).raw_host.decode("ascii"):
            raise
        raise HostDeferred(None) from None  # a redirect led where no request may go
    except DownloadError:
        raise HostDeferred(None) from None
    if 200 <= status < 300:
        return parse_robots(body.decode("utf-8", "replace"), product)
    if status == 429 or status >= 500:
        raise HostDeferred(status)
    return Rules()


def _spelled(text: str) -> str:
    """``text`` as RFC 9309 2.2.2 compares it: signs beyond ASCII and the space percent-encoded,
    the escape of an unreserved sign decoded, every other escape in capitals."""
    return _ESCAPE.sub(_escape, quote(text, safe=_AS_IT_IS))


def _escape(found: re.Match[str]) -> str:
    sign = chr(int(found.group(0)[1:], 16))
    return sign if sign in _UNRESERVED else found.group(0).upper()


def _matches(rule: str, target: str) -> bool:
    """``rule`` matches the start of ``target``, or all of it with a closing $."""
    return _whole(rule[:-1], target) if rule.endswith("$") else _whole(rule + "*", target)


def _whole(pattern: str, text: str) -> bool:
    """All of ``text`` as ``pattern`` reads it, * for any run of signs: the two-pointer walk, at
    most len(pattern) * len(text) steps, where a regex of many stars backtracks without end."""
    at = index = 0
    star = -1  # where the last star stood, and up to where in the text it had taken
    taken = 0
    while index < len(text):
        if at < len(pattern) and pattern[at] == "*":
            star, taken = at, index
            at += 1
        elif at < len(pattern) and pattern[at] == text[index]:
            at += 1
            index += 1
        elif star >= 0:
            at, taken = star + 1, taken + 1
            index = taken
        else:
            return False
    while at < len(pattern) and pattern[at] == "*":
        at += 1
    return at == len(pattern)
