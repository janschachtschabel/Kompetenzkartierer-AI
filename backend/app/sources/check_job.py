"""The job source.check: every address of the register's candidates looked at once (plan M1, 2.5;
Gesamtplan §7.5).

The candidates are the entries of no account - the seeds - with an address and no file yet. Each
address is asked once, however many entries hold it, unless a check found it out before: what
was found goes to url_check at once (app/db/url_checks.py), so a job run again - another attempt,
a later start - goes on where the last stopped, and a candidate seeded since at an address
checked before takes what was found there. The addresses are taken host by host in turn. Every
address asked, each redirect's too, first passes its origin's robots.txt (app/sources/robots.py)
- what it forbids is not fetched - and then waits for its host's turn (CHECK_HOST_INTERVAL_S across
all workers, app/sources/throttle.py); so does each address robots.txt is asked at, its redirects
followed. Nothing of a body is stored: it is streamed and hashed (app/sources/url_probe.py).

Nothing is got round: no other user agent, no archive or mirror instead. A server that asks to
wait (429, 503) is noted and holds its host off for as long as it says (Retry-After, a day at
most), its robots.txt's too; no answer for now (502, 504, a timeout, a broken connection) is
noted as unavailable. Both are asked again by a later check, and the host waits for it - its
other addresses, and every redirect to it - as does a host whose name does not resolve now or
whose robots.txt cannot be had now; their addresses are noted nowhere and stay unchecked. The
candidates at the address follow: reachable for an answer of 2xx, unreachable for any other or
none, unchanged for a request to wait.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from itertools import zip_longest
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx2
import psycopg

from app.db.url_checks import UrlCheck, catch_up, record_check, unchecked_addresses
from app.jobs.context import JobContext
from app.jobs.queue import Job, enqueue, report_progress
from app.sources.register import CheckOutcome, RegisterStatus
from app.sources.robots import HostDeferred, Rules, product_token, read_robots
from app.sources.throttle import hold_host, wait_turn
from app.sources.url_fetch import BadAnswer, DownloadError, HostNotResolved, TooManyRedirects, UrlNotAllowed
from app.sources.url_probe import Probe, probe

KIND = "source.check"
MIB = 2**20
MAX_HOST_SIGNS = 253  # what DNS holds: a longer name resolves nowhere (and host_throttle refuses it)
MAX_URL_SIGNS = 2000  # what url_check.final_url holds
# What the candidates at an address become; a request to wait leaves them as they were
REGISTER_STATUS: dict[CheckOutcome, RegisterStatus | None] = {
    "reachable": "reachable",
    "too_large": "reachable",
    "refused": "unreachable",
    "throttled": None,
    "server_error": "unreachable",
    "unavailable": "unreachable",
    "unreachable": "unreachable",
    "robots": "unreachable",
}
# What a later check asks again; the host's other addresses wait for it
ASKED_AGAIN: frozenset[CheckOutcome] = frozenset({"throttled", "unavailable"})
_ASKED_TO_WAIT = frozenset({429, 503})
_NO_ANSWER_NOW = frozenset({502, 504})
# A server's Retry-After holds its host off this long at most; a host whose next turn lies further
# off than HOST_WAIT_S gives no turn, its addresses waiting for a later check
MAX_RETRY_AFTER_S = 86_400.0
HOST_WAIT_S = 120.0
Sleep = Callable[[float], Awaitable[None]]
# One check at a time: two starts at once would each find none waiting and enqueue one
_START_LOCK = int.from_bytes(b"kka-chk", "big")


async def enqueue_check(connection: psycopg.AsyncConnection, lane: str) -> tuple[UUID | None, UUID | None]:
    """A new check of ``lane``, unless one waits or runs: (the new one, the one there). Called in a
    transaction, whose end releases the lock."""
    await connection.execute("SELECT pg_advisory_xact_lock(%s)", (_START_LOCK,))
    cursor = await connection.execute(
        "SELECT id FROM job WHERE kind = %s AND status IN ('queued', 'running') ORDER BY created_at LIMIT 1",
        (KIND,),
    )
    found = await cursor.fetchone()
    if found is not None:
        return None, found[0]
    return await enqueue(connection, KIND, lane, {}), None


@dataclass(frozen=True)
class Deferral:
    """The address waits for a later check, and so do the other addresses of ``host``."""

    host: str


async def check_sources(
    context: JobContext,
    job: Job,
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    sleep: Sleep = asyncio.sleep,
) -> dict[str, Any]:
    """Look at every address not checked for good; ``transport`` is the network and ``sleep`` the
    wait for a host's turn (tests). ``checked`` counts what was found for good, ``deferred`` what
    a later check asks again."""
    async with context.pool.connection() as connection:
        await catch_up(connection, REGISTER_STATUS)
        addresses = in_turn(await unchecked_addresses(connection, ASKED_AGAIN))
    look = _Look(context, transport, sleep)
    checked = deferred = 0
    for done, url in enumerate(addresses, start=1):
        host = urlsplit(url).hostname or ""
        found = Deferral(host) if host in look.deferred else await look.at(url, host)
        async with context.pool.connection() as connection:
            if isinstance(found, Deferral):
                look.deferred.add(found.host)
                deferred += 1
            else:
                await record_check(connection, found, REGISTER_STATUS[found.outcome])
                if found.outcome in ASKED_AGAIN:
                    look.deferred.add(look.host_asked)
                    deferred += 1
                else:
                    checked += 1
            await report_progress(connection, job, "checking", {"done": done, "total": len(addresses)})
    return {"checked": checked, "deferred": deferred, "deferred_hosts": sorted(look.deferred)}


def in_turn(addresses: list[str]) -> list[str]:
    """The addresses host by host in turn: a host's next one comes after every other host's."""
    by_host: dict[str, list[str]] = {}
    for url in addresses:
        by_host.setdefault(urlsplit(url).hostname or "", []).append(url)
    return [url for turn in zip_longest(*by_host.values()) for url in turn if url is not None]


class _NoHost:
    """An origin whose host is not to be asked at all: none of its addresses is."""


class _Forbidden(Exception):
    """robots.txt forbids the address the way leads to."""


class _NotToBeAsked(Exception):
    """The way leads to a host that is not to be asked."""


class _Wait(Exception):
    """The way leads to a host that waits for a later check."""

    def __init__(self, host: str) -> None:
        super().__init__(host)
        self.host = host


@dataclass
class _Look:
    context: JobContext
    transport: httpx2.AsyncBaseTransport | None
    sleep: Sleep
    robots: dict[str, Rules | _NoHost | None] = field(default_factory=dict)  # None: deferred
    host_asked: str = ""  # the host of the address asked last, redirects followed
    # the hosts that wait for a later check, however the way leads to them
    deferred: set[str] = field(default_factory=set)

    async def at(self, url: str, host: str) -> UrlCheck | Deferral:
        """What was found at ``url``, or that it waits for a later check."""
        self.host_asked = host
        if not host or len(host) > MAX_HOST_SIGNS:
            return UrlCheck(url, "unreachable")
        try:
            found = await probe(
                url,
                max_bytes=self.context.settings.max_upload_mb * MIB,
                transport=self.transport,
                user_agent=self.context.settings.fetch_user_agent,
                before_hop=self._hop,
            )
        except _Forbidden:
            return UrlCheck(url, "robots")
        except _Wait as waiting:
            return Deferral(waiting.host)
        except HostNotResolved as error:
            return Deferral(self.host_asked) if error.transient else UrlCheck(url, "unreachable")
        except (_NotToBeAsked, UrlNotAllowed, BadAnswer, TooManyRedirects):
            return UrlCheck(url, "unreachable")  # no answer there can be, or none that can be used
        except DownloadError:
            return UrlCheck(url, "unavailable")  # no answer for now: a timeout, a broken connection
        checked = _found(url, found)
        if checked.outcome == "throttled" and (seconds := _retry_after_s(found.retry_after)) is not None:
            async with self.context.pool.connection() as connection:
                await hold_host(connection, self.host_asked, seconds)
        return checked

    async def _hop(self, address: str) -> None:
        """Before each address the way asks: whether its host waits, its origin's robots.txt, then
        its host's turn. An address longer than the register holds (a redirect's: the seed's are
        no longer) is not asked, and the address it came from is unreachable: its server set it,
        and the rules of robots.txt are matched against all of it. No address of the way is
        longer than url_check.final_url holds, then."""
        parts = urlsplit(address)
        host = parts.hostname or ""
        self.host_asked = host
        if not host or len(host) > MAX_HOST_SIGNS or len(address) > MAX_URL_SIGNS:
            raise _NotToBeAsked
        if host in self.deferred:
            raise _Wait(host)
        # one origin however the address spells it: "WWW.Example.de" is where a redirect to
        # "www.example.de" leads
        rules = await self._rules(f"{parts.scheme.lower()}://{parts.netloc.lower()}")
        if rules is None:
            raise _Wait(host)
        if isinstance(rules, _NoHost):
            raise _NotToBeAsked
        if not rules.allows(address):
            raise _Forbidden
        if not await self._turn(host):
            raise _Wait(host)

    async def _rules(self, origin: str) -> Rules | _NoHost | None:
        if origin not in self.robots:
            self.robots[origin] = await self._read_rules(origin)
        return self.robots[origin]

    async def _read_rules(self, origin: str) -> Rules | _NoHost | None:
        """The origin's rules, robots.txt asked as a document is: each hop of its way in its
        host's turn, no host that waits asked. None: the origin waits for a later check, as does
        the host on the way asked last where robots.txt could not be had - the one that asked to
        wait, gave no answer now or sent it on to where no request may go."""
        settings = self.context.settings
        asked = ""  # the host robots.txt was asked of last, its redirects followed

        async def hop(address: str) -> None:
            nonlocal asked
            asked = urlsplit(address).hostname or ""
            askable = asked and len(asked) <= MAX_HOST_SIGNS and asked not in self.deferred
            if not askable or not await self._turn(asked):
                raise _Wait(asked)

        try:
            return await read_robots(
                origin,
                product_token(settings.fetch_user_agent),
                transport=self.transport,
                user_agent=settings.fetch_user_agent,
                before_hop=hop,
            )
        except _Wait:
            return None
        except HostDeferred as deferred:
            self.deferred.add(asked)
            if (seconds := _retry_after_s(deferred.retry_after)) is not None:
                async with self.context.pool.connection() as connection:
                    await hold_host(connection, asked, seconds)
            return None
        except HostNotResolved as error:
            return None if error.transient else _NoHost()
        except UrlNotAllowed:
            return _NoHost()

    async def _turn(self, host: str) -> bool:
        return await wait_turn(
            self.context.pool,
            host,
            self.context.settings.check_host_interval_s,
            sleep=self.sleep,
            max_wait_s=HOST_WAIT_S,
        )


def _found(url: str, found: Probe) -> UrlCheck:
    last = found.chain[-1]
    answered = UrlCheck(
        url,
        "refused",
        status_code=found.status_code,
        final_url=last if len(found.chain) > 1 else None,
        content_type=found.content_type,
        last_modified=found.last_modified,
    )
    if 200 <= found.status_code < 300:
        if found.too_large:
            return replace(answered, outcome="too_large", detected_type=found.kind)
        return replace(
            answered, outcome="reachable", detected_type=found.kind, size=found.size, sha256=found.sha256
        )
    if found.status_code in _ASKED_TO_WAIT:
        return replace(answered, outcome="throttled")
    if found.status_code in _NO_ANSWER_NOW:
        return replace(answered, outcome="unavailable")
    if found.status_code >= 500:
        return replace(answered, outcome="server_error")
    return answered  # 4xx, or a 1xx: the server answered, with no document


def _retry_after_s(value: str | None) -> float | None:
    """How long the server asked to wait (seconds, or a date), within a day; None if it said nothing
    that reads as either."""
    if value is None:
        return None
    if value.isascii() and value.isdigit():  # isdigit alone takes "²", which float() refuses
        seconds = float(value)
    else:
        try:
            until = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):  # OverflowError: a year past any datetime
            return None
        until = until if until.tzinfo else until.replace(tzinfo=UTC)
        seconds = (until - datetime.now(UTC)).total_seconds()
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_S)
