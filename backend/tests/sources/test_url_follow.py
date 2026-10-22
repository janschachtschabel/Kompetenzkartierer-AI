"""The way every request of the register goes (url_fetch.follow), as the check job needs it: a hook
before each address is asked, whose wait is no part of the deadline; no trace of ours to hosts of
others; and a name that does not resolve now told from one that never will (plan M1, 2.5)."""

import asyncio
import socket
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from app.core.tracing import take_trace_headers
from app.sources.url_fetch import (
    NOT_PUBLIC,
    DownloadError,
    HostNotResolved,
    HostRefused,
    UrlNotAllowed,
    follow,
    public_address,
)


def mock(handler: Callable[[httpx2.Request], Any]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


async def status_of(response: httpx2.Response) -> int:
    return response.status_code


def redirecting(request: httpx2.Request) -> httpx2.Response:
    if request.url.host == "a.example":
        return httpx2.Response(302, headers={"location": "https://b.example/b"})
    return httpx2.Response(200)


@pytest.mark.anyio
async def test_the_hook_hears_of_every_address_before_it_is_asked() -> None:
    asked: list[str] = []
    heard: list[tuple[str, int]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(str(request.url))
        return redirecting(request)

    async def before(url: str) -> None:
        heard.append((url, len(asked)))

    status, chain = await follow("https://a.example/a", status_of, transport=mock(handler), before_hop=before)

    assert status == 200
    assert heard == [("https://a.example/a", 0), ("https://b.example/b", 1)]
    assert chain == ["https://a.example/a", "https://b.example/b"]


@pytest.mark.anyio
async def test_what_the_hook_raises_ends_the_way_as_it_is() -> None:
    class Forbidden(Exception):
        pass

    asked: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(str(request.url))
        return redirecting(request)

    async def before(url: str) -> None:
        if url.startswith("https://b.example"):
            raise Forbidden

    with pytest.raises(Forbidden):
        await follow("https://a.example/a", status_of, transport=mock(handler), before_hop=before)
    assert asked == ["https://a.example/a"]


@pytest.mark.anyio
async def test_the_time_the_hook_waits_is_not_the_fetch_s() -> None:
    # a host's turn, its robots.txt: the wait is ours, not the server's
    async def waiting(url: str) -> None:
        await asyncio.sleep(0.3)

    status, _ = await follow(
        "https://a.example/a", status_of, transport=mock(redirecting), before_hop=waiting, total_timeout=0.2
    )

    assert status == 200


@pytest.mark.anyio
async def test_a_slow_answer_runs_into_the_deadline_all_the_same() -> None:
    async def late(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200)

    async def quick(url: str) -> None:
        return None

    with pytest.raises(DownloadError, match="too long"):
        await follow(
            "https://a.example/a", status_of, transport=mock(late), before_hop=quick, total_timeout=0.1
        )


@pytest.mark.anyio
async def test_the_trace_goes_along_only_where_it_is_asked_for() -> None:
    seen: list[httpx2.Headers] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers)
        return httpx2.Response(200)

    take_trace_headers([(b"x-client-trace-id", b"trace-of-the-check")], "request-1")
    await follow("https://a.example/", status_of, transport=mock(handler))
    await follow("https://a.example/", status_of, transport=mock(handler), trace=False)

    assert seen[0]["x-client-trace-id"] == "trace-of-the-check"
    assert "x-client-trace-id" not in seen[1]
    assert not {
        name for name in seen[1] if "request-id" in name or "trace" in name or name.startswith("x-b3")
    }


def test_a_name_that_does_not_resolve_now_is_told_from_one_that_never_will() -> None:
    def again(host: str) -> list[str]:
        raise socket.gaierror(socket.EAI_AGAIN, "temporary failure in name resolution")

    def nowhere(host: str) -> list[str]:
        raise socket.gaierror(socket.EAI_NONAME, "name or service not known")

    def unencodable(host: str) -> list[str]:
        raise UnicodeError("label too long")

    def broken(host: str) -> list[str]:
        raise OSError("the resolver could not be asked")

    found = {}
    for name, resolve in (
        ("again", again),
        ("nowhere", nowhere),
        ("unencodable", unencodable),
        ("broken", broken),
    ):
        with pytest.raises(HostNotResolved) as refused:
            public_address(f"{name}.example", resolve)
        found[name] = refused.value

    assert {name: error.transient for name, error in found.items()} == {
        "again": True,
        "nowhere": False,
        "unencodable": False,
        "broken": True,
    }
    assert found["again"].host == "again.example"
    # an account hears what it hears of an inside address: names tell nothing of the network
    assert {str(error) for error in found.values()} == {NOT_PUBLIC}


def test_an_inside_address_is_a_host_refused_by_name_not_one_that_did_not_resolve() -> None:
    with pytest.raises(HostRefused) as inside:
        public_address("intern.example", lambda host: ["10.1.2.3"])

    assert inside.value.host == "intern.example"
    assert not isinstance(inside.value, HostNotResolved)
    assert isinstance(inside.value, UrlNotAllowed)
