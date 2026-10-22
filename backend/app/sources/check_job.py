"""The job source.check: every address of the register's candidates looked at once (plan M1, 2.5;
Gesamtplan §7.5).

The candidates are the entries of no account - the seeds - with an address and no file yet. Each
address is asked once, however many entries hold it, unless a check found it out before: what
was found goes to url_check at once (app/db/url_checks.py), so a job run again - another attempt,
a later start - goes on where the last stopped. The addresses are taken host by host in turn,
each request in the host's slot (CHECK_HOST_INTERVAL_S across all workers, app/sources/throttle.py),
after the origin's robots.txt (app/sources/robots.py): what it forbids is not fetched. A 429 is
noted, not got round - no other user agent, no archive or mirror instead -: the address is asked
again by a later check, and so are the host's others; as are a host's whose robots.txt cannot be
had now. Nothing is stored but what was found: the body is streamed and hashed
(app/sources/url_probe.py). The candidates at the address follow: reachable for an answer of 2xx,
unreachable for any other or none, unchanged for a 429.

simplify: robots.txt and the slots are the first address's host's; a redirect to another host is
followed without asking its robots.txt or waiting its turn - a curriculum portal's download link
rarely leaves the portal, and a later check could ask every host on the way.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from itertools import zip_longest
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx2
import psycopg

from app.db.url_checks import UrlCheck, record_check, unchecked_addresses
from app.jobs.context import JobContext
from app.jobs.queue import Job, enqueue, report_progress
from app.sources.register import CheckOutcome, RegisterStatus
from app.sources.robots import HostDeferred, Rules, product_token, read_robots
from app.sources.throttle import wait_turn
from app.sources.url_fetch import DownloadError, UrlNotAllowed
from app.sources.url_probe import Probe, probe

KIND = "source.check"
MIB = 2**20
MAX_HOST_SIGNS = 253  # what DNS holds: a longer name resolves nowhere (and host_throttle refuses it)
MAX_URL_SIGNS = 2000  # what url_check.final_url holds
# What the candidates at an address become; a 429 leaves them as they were
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


async def check_sources(
    context: JobContext,
    job: Job,
    *,
    transport: httpx2.AsyncBaseTransport | None = None,
    sleep: Sleep = asyncio.sleep,
) -> dict[str, Any]:
    """Look at every unchecked address; ``transport`` is the network and ``sleep`` the wait for a
    host's turn (tests)."""
    async with context.pool.connection() as connection:
        addresses = in_turn(await unchecked_addresses(connection))
    look = _Look(context, transport, sleep)
    deferred_hosts: set[str] = set()
    checked = deferred = 0
    for done, url in enumerate(addresses, start=1):
        host = urlsplit(url).hostname or ""
        found = None if host in deferred_hosts else await look.at(url, host)
        if found is None:  # the host waits for a later check
            deferred_hosts.add(host)
            deferred += 1
        else:
            async with context.pool.connection() as connection:
                await record_check(connection, found, REGISTER_STATUS[found.outcome])
            checked += 1
            if found.outcome == "throttled":
                deferred_hosts.add(host)
        async with context.pool.connection() as connection:
            await report_progress(connection, job, "checking", {"done": done, "total": len(addresses)})
    return {"checked": checked, "deferred": deferred, "deferred_hosts": sorted(deferred_hosts)}


def in_turn(addresses: list[str]) -> list[str]:
    """The addresses host by host in turn: a host's next one comes after every other host's."""
    by_host: dict[str, list[str]] = {}
    for url in addresses:
        by_host.setdefault(urlsplit(url).hostname or "", []).append(url)
    return [url for turn in zip_longest(*by_host.values()) for url in turn if url is not None]


class _NoHost:
    """An origin whose host is not publicly reachable: none of its addresses is asked."""


@dataclass
class _Look:
    context: JobContext
    transport: httpx2.AsyncBaseTransport | None
    sleep: Sleep
    robots: dict[str, Rules | _NoHost | None] = field(default_factory=dict)  # None: deferred

    async def at(self, url: str, host: str) -> UrlCheck | None:
        """What was found at ``url``; None when its host waits for a later check."""
        if not host or len(host) > MAX_HOST_SIGNS:
            return UrlCheck(url, "unreachable")
        parts = urlsplit(url)
        rules = await self._rules(f"{parts.scheme}://{parts.netloc}", host)
        if rules is None:
            return None
        if isinstance(rules, _NoHost):
            return UrlCheck(url, "unreachable")
        if not rules.allows(url):
            return UrlCheck(url, "robots")
        await self._turn(host)
        try:
            found = await probe(
                url,
                max_bytes=self.context.settings.max_upload_mb * MIB,
                transport=self.transport,
                user_agent=self.context.settings.fetch_user_agent,
            )
        except (UrlNotAllowed, DownloadError):  # no answer, none in time, none that can be used
            return UrlCheck(url, "unreachable")
        return _found(url, found)

    async def _rules(self, origin: str, host: str) -> Rules | _NoHost | None:
        if origin not in self.robots:
            await self._turn(host)
            settings = self.context.settings
            try:
                self.robots[origin] = await read_robots(
                    origin,
                    product_token(settings.fetch_user_agent),
                    transport=self.transport,
                    user_agent=settings.fetch_user_agent,
                )
            except HostDeferred:
                self.robots[origin] = None
            except UrlNotAllowed:
                self.robots[origin] = _NoHost()
        return self.robots[origin]

    async def _turn(self, host: str) -> None:
        await wait_turn(
            self.context.pool, host, self.context.settings.check_host_interval_s, sleep=self.sleep
        )


def _found(url: str, found: Probe) -> UrlCheck:
    last = found.chain[-1]
    answered = UrlCheck(
        url,
        "refused",
        status_code=found.status_code,
        final_url=last if len(found.chain) > 1 and len(last) <= MAX_URL_SIGNS else None,
        content_type=found.content_type,
        last_modified=found.last_modified,
    )
    if 200 <= found.status_code < 300:
        if found.too_large:
            return replace(answered, outcome="too_large", detected_type=found.kind)
        return replace(
            answered, outcome="reachable", detected_type=found.kind, size=found.size, sha256=found.sha256
        )
    if found.status_code == 429:
        return replace(answered, outcome="throttled")
    if found.status_code >= 500:
        return replace(answered, outcome="server_error")
    return answered  # 4xx, or a 1xx or 3xx no redirect: the server answered, with no document
