"""The job source.check: every address of the register's candidates looked at once (plan M1, 2.5).

The network is a mock transport of invented hosts; the database is real, the store a folder that
must stay empty. Waiting for a host's turn is recorded, not slept.
"""

import hashlib
import socket
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path
from typing import Any, get_args
from uuid import UUID

import httpx2
import pytest
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.ids import new_id
from app.core.storage import FileSystemStorage
from app.core.storage_async import AsyncStorage
from app.db.accounts import create_account
from app.db.migrate import migrate
from app.jobs.context import JobContext
from app.jobs.handlers import make_handlers
from app.jobs.queue import Job, claim, enqueue
from app.sources.check_job import KIND, MAX_RETRY_AFTER_S, REGISTER_STATUS, _retry_after_s, check_sources
from app.sources.register import CheckOutcome
from app.sources.url_fetch import HostNotResolved, HostRefused, PinnedBackend, pinned_transport
from tests.sources.compressed import MIB, arriving, in_chunks
from tests.support import make_settings

pytestmark = [pytest.mark.pg, pytest.mark.anyio]

PDF = b"%PDF-1.7 " + b"Lehrplan " * 500
HTML = b"<!DOCTYPE html><html><body>Lehrplan</body></html>"
SEED = "vergleichsdatensatz-v62.493"
Answer = Callable[[httpx2.Request], httpx2.Response]


def reply(status: int = 200, body: bytes = b"", /, **headers: str) -> Answer:
    return lambda request: httpx2.Response(status, content=body, headers=headers)


class Network:
    """The hosts of a test: answers by host and path (404 for any other), every request kept."""

    def __init__(self, answers: dict[str, Answer]) -> None:
        self.answers = answers
        self.asked: list[httpx2.Request] = []

    def transport(self) -> httpx2.MockTransport:
        def handler(request: httpx2.Request) -> httpx2.Response:
            self.asked.append(request)
            answer = self.answers.get(f"{request.url.host}{request.url.path}")
            return answer(request) if answer else httpx2.Response(404)

        return httpx2.MockTransport(handler)

    def paths(self) -> list[str]:
        return [f"{request.url.host}{request.url.path}" for request in self.asked]


@pytest.fixture
async def context(database_url: str, tmp_path: Path) -> AsyncIterator[JobContext]:
    migrate(database_url)
    async with AsyncConnectionPool(database_url, min_size=1, max_size=4, open=False) as pool:
        storage = AsyncStorage(FileSystemStorage(tmp_path / "store"))
        yield JobContext(pool=pool, storage=storage, settings=make_settings(database_url=database_url))


async def add_entry(context: JobContext, url: str, **columns: Any) -> UUID:
    """A register entry; of no account, from the seed, unless ``columns`` say otherwise."""
    source_id = new_id()
    values = {"provenance": SEED, "url": url, **columns}
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    async with context.pool.connection() as connection:
        await connection.execute("INSERT INTO entity (id, kind) VALUES (%s, 'source')", (source_id,))
        await connection.execute(
            f"INSERT INTO source (id, {names}) VALUES (%s, {marks})",  # noqa: S608 - the test's own names
            (source_id, *values.values()),
        )
    return source_id


async def add_acquired(context: JobContext, url: str) -> UUID:
    file_id = new_id()
    async with context.pool.connection() as connection:
        await connection.execute(
            "INSERT INTO source_file (id, sha256, size_bytes, storage_key) VALUES (%s, %s, 4, %s)",
            (file_id, new_id().bytes * 2, f"sources/{file_id}"),
        )
    return await add_entry(
        context, url, file_id=file_id, file_name="lp.pdf", mime="application/pdf", register_status="acquired"
    )


async def add_owned(context: JobContext, url: str) -> UUID:
    async with context.pool.connection() as connection:
        owner = await create_account(connection, f"Lehrkraft {new_id()}", ["nutzer"])
    return await add_entry(context, url, owner_id=owner, provenance="url")


async def a_job(context: JobContext) -> Job:
    async with context.pool.connection() as connection:
        await enqueue(connection, KIND, "admin", {})
        job = await claim(connection, "w1", [KIND], 60)
    assert job is not None
    return job


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


async def run(context: JobContext, network: Network, sleeps: Sleeps | None = None) -> dict[str, Any]:
    return await check_sources(
        context, await a_job(context), transport=network.transport(), sleep=sleeps or Sleeps()
    )


async def checks(context: JobContext) -> dict[str, dict[str, Any]]:
    async with context.pool.connection() as connection:
        cursor = connection.cursor(row_factory=dict_row)
        await cursor.execute("SELECT * FROM url_check")
        return {row["url"]: row for row in await cursor.fetchall()}


async def status_of(context: JobContext, source_id: UUID) -> str:
    async with context.pool.connection() as connection:
        cursor = await connection.execute("SELECT register_status FROM source WHERE id = %s", (source_id,))
        found = await cursor.fetchone()
    assert found is not None
    return str(found[0])


A = "https://a.example"
SITE_A = {
    "a.example/lp.pdf": reply(
        200, PDF, **{"content-type": "application/pdf", "last-modified": "Wed, 01 Jul 2026"}
    ),
    "a.example/gone": reply(404),
    "a.example/forbidden": reply(403),
    "a.example/broken": reply(500),
    "a.example/start": reply(302, location="/seite.html"),
    "a.example/seite.html": reply(200, HTML, **{"content-type": "text/html"}),
}


async def test_each_address_is_asked_once_and_what_it_answered_kept(context: JobContext) -> None:
    for path in ("/lp.pdf", "/lp.pdf", "/gone", "/forbidden", "/broken", "/start"):
        await add_entry(context, A + path)
    network = Network(SITE_A)

    result = await run(context, network)

    found = await checks(context)
    asked_once = ["robots.txt", "lp.pdf", "gone", "forbidden", "broken", "start", "seite.html"]
    assert sorted(network.paths()) == sorted(f"a.example/{path}" for path in asked_once)
    pdf = found[A + "/lp.pdf"]
    assert (pdf["outcome"], pdf["status_code"], pdf["detected_type"]) == ("reachable", 200, "pdf")
    assert (pdf["size_bytes"], bytes(pdf["sha256"])) == (len(PDF), hashlib.sha256(PDF).digest())
    assert (pdf["content_type"], pdf["last_modified"], pdf["final_url"]) == (
        "application/pdf",
        "Wed, 01 Jul 2026",
        None,
    )
    outcomes = {url: (row["outcome"], row["status_code"]) for url, row in found.items()}
    assert outcomes[A + "/gone"] == ("refused", 404)
    assert outcomes[A + "/forbidden"] == ("refused", 403)
    assert outcomes[A + "/broken"] == ("server_error", 500)
    moved = found[A + "/start"]
    assert (moved["outcome"], moved["detected_type"], moved["final_url"]) == (
        "reachable",
        "html",
        A + "/seite.html",
    )
    assert result == {"checked": 5, "deferred": 0, "deferred_hosts": []}


async def test_the_register_follows_what_the_check_found(context: JobContext) -> None:
    shared = [await add_entry(context, A + "/lp.pdf") for _ in range(2)]
    gone, broken = await add_entry(context, A + "/gone"), await add_entry(context, A + "/broken")
    acquired = await add_acquired(context, A + "/gone")
    owned, only_owned = await add_owned(context, A + "/gone"), await add_owned(context, A + "/mine")
    network = Network(SITE_A)

    await run(context, network)

    assert [await status_of(context, entry) for entry in shared] == ["reachable", "reachable"]
    assert (await status_of(context, gone), await status_of(context, broken)) == (
        "unreachable",
        "unreachable",
    )
    assert await status_of(context, acquired) == "acquired"
    # an account's entry is its owner's to fetch: neither asked for nor changed
    assert (await status_of(context, owned), await status_of(context, only_owned)) == (
        "unchecked",
        "unchecked",
    )
    assert "a.example/mine" not in network.paths()


async def test_a_server_that_asks_to_wait_is_noted_not_got_round(context: JobContext) -> None:
    waiting, later = (
        await add_entry(context, "https://b.example/x"),
        await add_entry(context, "https://b.example/y"),
    )
    await add_entry(context, A + "/lp.pdf")
    network = Network(
        {**SITE_A, "b.example/x": reply(429, **{"retry-after": "120"}), "b.example/y": reply(200, PDF)}
    )

    result = await run(context, network)

    found = await checks(context)
    assert (found["https://b.example/x"]["outcome"], found["https://b.example/x"]["status_code"]) == (
        "throttled",
        429,
    )
    assert "https://b.example/y" not in found
    # the host's other addresses wait for a later check: no other agent, no archive, no mirror
    assert [path for path in network.paths() if path.startswith("b.")] == [
        "b.example/robots.txt",
        "b.example/x",
    ]
    assert {request.url.host for request in network.asked} == {"a.example", "b.example"}
    assert {request.headers["user-agent"] for request in network.asked} == {context.settings.fetch_user_agent}
    assert (await status_of(context, waiting), await status_of(context, later)) == ("unchecked", "unchecked")
    assert result == {"checked": 1, "deferred": 2, "deferred_hosts": ["b.example"]}


async def test_a_job_run_again_asks_only_what_is_unchecked_and_where_it_was_asked_to_wait(
    context: JobContext,
) -> None:
    for url in ("https://b.example/x", "https://b.example/y", A + "/lp.pdf"):
        await add_entry(context, url)
    await run(context, Network({**SITE_A, "b.example/x": reply(429)}))
    network = Network({**SITE_A, "b.example/x": reply(200, PDF), "b.example/y": reply(200, PDF)})

    result = await run(context, network)

    assert sorted(network.paths()) == ["b.example/robots.txt", "b.example/x", "b.example/y"]
    assert (await checks(context))["https://b.example/x"]["outcome"] == "reachable"
    assert result == {"checked": 2, "deferred": 0, "deferred_hosts": []}


async def test_what_robots_txt_forbids_is_not_fetched(context: JobContext) -> None:
    forbidden = await add_entry(context, "https://c.example/intern/lp.pdf")
    await add_entry(context, "https://c.example/lp.pdf")
    rules = reply(200, b"User-agent: *\nDisallow: /intern/\n")
    network = Network({"c.example/robots.txt": rules, "c.example/lp.pdf": reply(200, PDF)})

    await run(context, network)

    intern = (await checks(context))["https://c.example/intern/lp.pdf"]
    assert network.paths() == ["c.example/robots.txt", "c.example/lp.pdf"]
    assert (intern["outcome"], intern["status_code"]) == ("robots", None)
    assert await status_of(context, forbidden) == "unreachable"


async def test_a_host_whose_robots_txt_cannot_be_had_now_waits_for_a_later_check(context: JobContext) -> None:
    entry = await add_entry(context, "https://d.example/lp.pdf")
    network = Network({"d.example/robots.txt": reply(503), "d.example/lp.pdf": reply(200, PDF)})

    result = await run(context, network)

    assert network.paths() == ["d.example/robots.txt"]
    assert await checks(context) == {}
    assert await status_of(context, entry) == "unchecked"
    assert result == {"checked": 0, "deferred": 1, "deferred_hosts": ["d.example"]}


async def test_a_host_not_publicly_reachable_is_unreachable_and_asked_no_more(context: JobContext) -> None:
    entries = [await add_entry(context, f"https://intern.example/{name}") for name in ("a.pdf", "b.pdf")]

    def inside(request: httpx2.Request) -> httpx2.Response:
        # as the pinned transport refuses a host that resolves inside the network
        raise HostRefused("intern.example")

    network = Network({"intern.example/robots.txt": inside})

    await run(context, network)

    assert network.paths() == ["intern.example/robots.txt"]
    assert {row["outcome"] for row in (await checks(context)).values()} == {"unreachable"}
    assert [await status_of(context, entry) for entry in entries] == ["unreachable", "unreachable"]


async def test_no_answer_for_now_is_unavailable_and_a_redirect_loop_unreachable(context: JobContext) -> None:
    urls = ["https://e1.example/lp.pdf", "https://e2.example/slow.pdf", "https://e3.example/loop"]
    entries = [await add_entry(context, url) for url in urls]

    def refusing(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    def slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out")

    network = Network(
        {
            "e1.example/lp.pdf": refusing,
            "e2.example/slow.pdf": slow,
            "e3.example/loop": reply(302, location="/loop"),
        }
    )

    result = await run(context, network)

    found = await checks(context)
    assert {url: (row["outcome"], row["status_code"]) for url, row in found.items()} == {
        "https://e1.example/lp.pdf": ("unavailable", None),
        "https://e2.example/slow.pdf": ("unavailable", None),
        "https://e3.example/loop": ("unreachable", None),
    }
    # unreachable for now; a later check asks again
    assert [await status_of(context, entry) for entry in entries] == ["unreachable"] * 3
    assert result == {"checked": 1, "deferred": 2, "deferred_hosts": ["e1.example", "e2.example"]}


@pytest.mark.parametrize(
    ("status", "outcome"), [(503, "throttled"), (502, "unavailable"), (504, "unavailable")]
)
async def test_a_host_that_asks_to_wait_or_gives_no_answer_now_is_asked_no_more_this_time(
    context: JobContext, status: int, outcome: str
) -> None:
    first, later = (
        await add_entry(context, "https://b.example/x"),
        await add_entry(context, "https://b.example/y"),
    )
    network = Network({"b.example/x": reply(status), "b.example/y": reply(200, PDF)})

    result = await run(context, network)

    found = await checks(context)
    assert (found["https://b.example/x"]["outcome"], found["https://b.example/x"]["status_code"]) == (
        outcome,
        status,
    )
    assert "b.example/y" not in network.paths()
    assert (await status_of(context, first), await status_of(context, later)) == (
        "unchecked" if outcome == "throttled" else "unreachable",
        "unchecked",
    )
    assert result == {"checked": 0, "deferred": 2, "deferred_hosts": ["b.example"]}


async def test_a_host_whose_server_asked_for_an_hour_is_not_asked_by_a_check_within_it(
    context: JobContext,
) -> None:
    await add_entry(context, "https://b.example/x")
    await add_entry(context, A + "/lp.pdf")
    await run(context, Network({**SITE_A, "b.example/x": reply(429, **{"retry-after": "3600"})}))
    network = Network({**SITE_A, "b.example/x": reply(200, PDF)})

    result = await run(context, network)

    assert [path for path in network.paths() if path.startswith("b.")] == []
    assert result == {"checked": 0, "deferred": 1, "deferred_hosts": ["b.example"]}


async def test_an_address_given_no_answer_for_now_is_asked_again_by_the_next_check(
    context: JobContext,
) -> None:
    entry = await add_entry(context, "https://e.example/lp.pdf")

    def refusing(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    await run(context, Network({"e.example/lp.pdf": refusing}))
    result = await run(context, Network({"e.example/lp.pdf": reply(200, PDF)}))

    assert (await checks(context))["https://e.example/lp.pdf"]["outcome"] == "reachable"
    assert await status_of(context, entry) == "reachable"
    assert result == {"checked": 1, "deferred": 0, "deferred_hosts": []}


async def test_an_answer_with_no_http_status_is_unreachable_and_ends_no_check(context: JobContext) -> None:
    await add_entry(context, "https://b.example/odd")
    await add_entry(context, A + "/lp.pdf")

    def odd(request: httpx2.Request) -> httpx2.Response:
        response = httpx2.Response(200, content=PDF)
        response.status_code = 999  # as h11 takes it, LinkedIn's answer to a robot
        return response

    await run(context, Network({**SITE_A, "b.example/odd": odd}))

    found = await checks(context)
    assert (found["https://b.example/odd"]["outcome"], found["https://b.example/odd"]["status_code"]) == (
        "unreachable",
        None,
    )
    assert found[A + "/lp.pdf"]["outcome"] == "reachable"


async def test_a_redirect_to_what_robots_txt_forbids_on_the_same_host_is_not_followed(
    context: JobContext,
) -> None:
    entry = await add_entry(context, "https://c.example/start")
    network = Network(
        {
            "c.example/robots.txt": reply(200, b"User-agent: *\nDisallow: /intern/\n"),
            "c.example/start": reply(302, location="/intern/lp.pdf"),
            "c.example/intern/lp.pdf": reply(200, PDF),
        }
    )

    await run(context, network)

    assert network.paths() == ["c.example/robots.txt", "c.example/start"]
    assert (await checks(context))["https://c.example/start"]["outcome"] == "robots"
    assert await status_of(context, entry) == "unreachable"


async def test_a_redirect_to_another_host_asks_its_robots_txt_first(context: JobContext) -> None:
    await add_entry(context, "https://a.example/start")
    network = Network(
        {
            "a.example/start": reply(302, location="https://z.example/privat/lp.pdf"),
            "z.example/robots.txt": reply(200, b"User-agent: *\nDisallow: /privat/\n"),
            "z.example/privat/lp.pdf": reply(200, PDF),
        }
    )

    await run(context, network)

    assert network.paths() == ["a.example/robots.txt", "a.example/start", "z.example/robots.txt"]
    assert (await checks(context))["https://a.example/start"]["outcome"] == "robots"


async def test_each_hop_takes_its_host_s_turn(context: JobContext) -> None:
    await add_entry(context, "https://a.example/1")
    hops = {f"a.example/{step}": reply(302, location=f"/{step + 1}") for step in (1, 2, 3)}
    network = Network({**hops, "a.example/4": reply(200, PDF)})
    sleeps = Sleeps()

    await run(context, network, sleeps)

    assert network.paths() == [
        "a.example/robots.txt",
        "a.example/1",
        "a.example/2",
        "a.example/3",
        "a.example/4",
    ]
    # robots.txt takes the first turn; each hop the next, CHECK_HOST_INTERVAL_S (2 s) apart
    assert [round(wait) for wait in sleeps.waits] == [2, 4, 6, 8]


async def test_a_redirect_to_a_host_that_waits_defers_that_host_not_the_first(context: JobContext) -> None:
    await add_entry(context, "https://a.example/start")
    await add_entry(context, A + "/lp.pdf")
    await add_entry(context, "https://z.example/other.pdf")
    network = Network(
        {
            **SITE_A,
            "a.example/start": reply(302, location="https://z.example/lp.pdf"),
            "z.example/robots.txt": reply(503),
        }
    )

    result = await run(context, network)

    assert (await checks(context))[A + "/lp.pdf"]["outcome"] == "reachable"
    assert "https://a.example/start" not in await checks(context)
    assert result["deferred_hosts"] == ["z.example"]


def resolving(names: dict[str, int]) -> httpx2.AsyncBaseTransport:
    """The pinned transport over a resolver that fails each name with its error, connecting nowhere."""

    def resolve(host: str) -> list[str]:
        raise socket.gaierror(names[host], "no address")

    return pinned_transport(PinnedBackend(resolve))


async def test_a_name_that_does_not_resolve_now_waits_and_one_that_never_will_is_unreachable(
    context: JobContext,
) -> None:
    again = await add_entry(context, "https://again.example/lp.pdf")
    nowhere = await add_entry(context, "https://nowhere.example/lp.pdf")

    result = await check_sources(
        context,
        await a_job(context),
        transport=resolving({"again.example": socket.EAI_AGAIN, "nowhere.example": socket.EAI_NONAME}),
        sleep=Sleeps(),
    )

    found = await checks(context)
    assert "https://again.example/lp.pdf" not in found
    assert found["https://nowhere.example/lp.pdf"]["outcome"] == "unreachable"
    assert (await status_of(context, again), await status_of(context, nowhere)) == (
        "unchecked",
        "unreachable",
    )
    assert result["deferred_hosts"] == ["again.example"]


async def test_a_candidate_seeded_after_its_address_was_checked_follows_what_was_found(
    context: JobContext,
) -> None:
    await add_entry(context, A + "/lp.pdf")
    await run(context, Network(SITE_A))
    later = await add_entry(context, A + "/lp.pdf")
    network = Network(SITE_A)

    result = await run(context, network)

    assert await status_of(context, later) == "reachable"
    assert network.asked == []
    assert result == {"checked": 0, "deferred": 0, "deferred_hosts": []}


async def test_what_was_found_stays_when_the_run_breaks_off(context: JobContext) -> None:
    await add_entry(context, A + "/lp.pdf")
    await add_entry(context, "https://b.example/x")

    def breaking(request: httpx2.Request) -> httpx2.Response:
        raise RuntimeError("the worker went down")

    with pytest.raises(RuntimeError):
        await run(context, Network({**SITE_A, "b.example/x": breaking}))

    assert (await checks(context))[A + "/lp.pdf"]["outcome"] == "reachable"


async def test_a_file_past_the_upload_limit_is_reachable_and_unhashed(context: JobContext) -> None:
    entry = await add_entry(context, A + "/gross.pdf")
    large = PDF + b"0" * (2 * MIB)
    streaming = {
        "a.example/gross.pdf": lambda request: httpx2.Response(200, content=arriving(in_chunks(large)))
    }

    await check_sources(
        replace(context, settings=make_settings(max_upload_mb=1)),
        await a_job(context),
        transport=Network(streaming).transport(),
        sleep=Sleeps(),
    )

    found = (await checks(context))[A + "/gross.pdf"]
    assert (found["outcome"], found["detected_type"], found["size_bytes"], found["sha256"]) == (
        "too_large",
        "pdf",
        None,
        None,
    )
    assert await status_of(context, entry) == "reachable"


async def test_a_host_name_no_dns_could_hold_is_unreachable_unasked(context: JobContext) -> None:
    host = ".".join(["a" * 63] * 4) + ".example"  # 263 signs: past what DNS holds
    await add_entry(context, f"https://{host}/lp.pdf")
    network = Network({})

    await run(context, network)

    assert network.asked == []
    assert (await checks(context))[f"https://{host}/lp.pdf"]["outcome"] == "unreachable"


async def test_a_host_is_asked_once_per_interval_and_the_hosts_in_turn(context: JobContext) -> None:
    for url in ("https://a.example/1", "https://a.example/2", "https://b.example/1", "https://b.example/2"):
        await add_entry(context, url)
    sleeps = Sleeps()
    network = Network({})

    await run(context, network, sleeps)

    assert [request.url.host for request in network.asked] == [
        "a.example", "a.example", "b.example", "b.example", "a.example", "b.example"
    ]  # fmt: skip
    # robots.txt takes the host's first turn; each next one comes CHECK_HOST_INTERVAL_S (2 s) later
    assert [round(wait) for wait in sorted(sleeps.waits)] == [2, 2, 4, 4]


async def test_nothing_of_a_body_is_stored(context: JobContext, tmp_path: Path) -> None:
    await add_entry(context, A + "/lp.pdf")

    await run(context, Network(SITE_A))

    assert [path for path in (tmp_path / "store").rglob("*") if path.is_file()] == []


async def test_the_check_reports_how_far_it_has_come(context: JobContext) -> None:
    for path in ("/lp.pdf", "/gone"):
        await add_entry(context, A + path)
    job = await a_job(context)

    await check_sources(context, job, transport=Network(SITE_A).transport(), sleep=Sleeps())

    async with context.pool.connection() as connection:
        cursor = await connection.execute("SELECT progress FROM job WHERE id = %s", (job.id,))
        found = await cursor.fetchone()
    assert found is not None
    assert found[0] == {"code": "checking", "params": {"done": 2, "total": 2}}


async def test_the_worker_knows_the_check(context: JobContext) -> None:
    assert KIND == "source.check"
    assert KIND in make_handlers(context)


def test_every_outcome_says_what_becomes_of_the_register() -> None:
    assert set(REGISTER_STATUS) == set(get_args(CheckOutcome))
    # what is asked again by a later check leaves the register or marks it for now, never acquired
    assert REGISTER_STATUS["unavailable"] == "unreachable"


def test_a_wait_is_read_in_seconds_or_as_a_date_within_a_day() -> None:
    in_an_hour = format_datetime(datetime.now(UTC) + timedelta(hours=1), usegmt=True)
    gone = format_datetime(datetime.now(UTC) - timedelta(hours=1), usegmt=True)

    assert _retry_after_s("120") == 120
    assert 3500 < (_retry_after_s(in_an_hour) or 0) <= 3600
    assert _retry_after_s(gone) == 0
    assert _retry_after_s(str(10 * 86_400)) == MAX_RETRY_AFTER_S
    assert _retry_after_s("bald") is None
    assert _retry_after_s(None) is None


@pytest.mark.parametrize(("transient", "outcome"), [(True, None), (False, "unreachable")])
async def test_a_document_whose_host_stops_resolving_waits_or_is_unreachable(
    context: JobContext, transient: bool, outcome: str | None
) -> None:
    # robots.txt came; the document's own connection finds the name gone, as the pinned transport would
    await add_entry(context, "https://b.example/lp.pdf")

    def gone(request: httpx2.Request) -> httpx2.Response:
        raise HostNotResolved("b.example", transient=transient)

    result = await run(context, Network({"b.example/lp.pdf": gone}))

    found = await checks(context)
    assert (found["https://b.example/lp.pdf"]["outcome"] if found else None) == outcome
    assert result["deferred_hosts"] == (["b.example"] if transient else [])


async def test_what_the_register_reached_otherwise_is_not_overwritten_by_an_older_check(
    context: JobContext,
) -> None:
    entry = await add_entry(context, A + "/lp.pdf", register_status="reachable")
    async with context.pool.connection() as connection:
        await connection.execute(
            "INSERT INTO url_check (url_sha256, url, outcome, status_code)"
            " VALUES (sha256(convert_to(%(url)s, 'UTF8')), %(url)s, 'refused', 404)",
            {"url": A + "/lp.pdf"},
        )

    await run(context, Network({}))

    assert await status_of(context, entry) == "reachable"
