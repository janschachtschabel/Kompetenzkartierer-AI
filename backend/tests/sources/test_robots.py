"""What a host's robots.txt allows the check job (RFC 9309; plan M1, 2.5): the longest rule wins,
an allow a tie; our own group, else that of "*"; and what to do when the file cannot be had."""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx2
import pytest

from app.core.tracing import take_trace_headers
from app.sources.robots import (
    MAX_RULE_SIGNS,
    MAX_RULES,
    ROBOTS_BYTES,
    HostDeferred,
    Rules,
    parse_robots,
    product_token,
    read_robots,
)
from app.sources.url_fetch import UrlNotAllowed
from tests.sources.compressed import CHUNK, MIB, arriving, in_chunks

PRODUCT = "Kompetenzkartierer-AI"
SITE = "https://lehrplaene.example"


def allows(text: str, path: str) -> bool:
    return parse_robots(text, PRODUCT).allows(f"{SITE}{path}")


def test_no_rules_allow_everything() -> None:
    assert allows("", "/lp.pdf")
    assert Rules().allows(f"{SITE}/intern/lp.pdf")


def test_a_disallow_of_everything_spares_robots_txt_itself() -> None:
    text = "User-agent: *\nDisallow: /\n"

    assert not allows(text, "/lp.pdf")
    assert allows(text, "/robots.txt")


def test_our_group_comes_before_that_of_everyone() -> None:
    text = "User-agent: *\nDisallow: /\n\nUser-agent: Kompetenzkartierer-AI\nAllow: /\n"

    assert allows(text, "/lp.pdf")


def test_robots_named_one_after_another_share_their_group() -> None:
    # an empty line ends nothing: both agents name one group, which says no to all
    assert not allows("User-agent: Kompetenzkartierer-AI\n\nUser-agent: *\nDisallow: /\n", "/lp.pdf")


def test_with_a_group_of_our_own_everyone_s_rules_do_not_count() -> None:
    assert allows("User-agent: Kompetenzkartierer-AI\nAllow: /x\n\nUser-agent: *\nDisallow: /\n", "/lp.pdf")


def test_our_token_is_matched_without_regard_to_case_or_version() -> None:
    for agent in ("kompetenzkartierer-ai", "KOMPETENZKARTIERER-AI", "Kompetenzkartierer-AI/2.0"):
        assert not allows(f"User-agent: {agent}\nDisallow: /\n", "/lp.pdf")


def test_another_robot_s_group_is_not_ours() -> None:
    assert allows("User-agent: Googlebot\nDisallow: /\n", "/lp.pdf")
    assert allows("User-agent: Kompetenzkartierer\nDisallow: /\n", "/lp.pdf")


def test_a_group_may_name_several_robots_and_our_groups_are_combined() -> None:
    text = (
        "User-agent: Googlebot\nUser-agent: Kompetenzkartierer-AI\nDisallow: /a/\n\n"
        "User-agent: Kompetenzkartierer-AI\nDisallow: /b/\n"
    )

    assert not allows(text, "/a/lp.pdf")
    assert not allows(text, "/b/lp.pdf")
    assert allows(text, "/c/lp.pdf")


def test_the_longest_rule_wins_whichever_comes_first() -> None:
    # urllib.robotparser takes the first that matches, and would allow /intern/ here
    assert not allows("User-agent: *\nAllow: /\nDisallow: /intern\n", "/intern/lp.pdf")
    assert allows("User-agent: *\nDisallow: /\nAllow: /lehrplaene/\n", "/lehrplaene/lp.pdf")
    assert not allows("User-agent: *\nDisallow: /\nAllow: /lehrplaene/\n", "/archiv/lp.pdf")


def test_an_allow_wins_a_tie() -> None:
    assert allows("User-agent: *\nDisallow: /lp\nAllow: /lp\n", "/lp.pdf")


@pytest.mark.parametrize(
    ("rule", "path", "allowed"),
    [
        ("/*.pdf$", "/medien/lp.pdf", False),
        ("/*.pdf$", "/medien/lp.pdf?v=1", True),
        ("/*?", "/medien/lp.pdf?v=1", False),
        ("/*?", "/medien/lp.pdf", True),
        ("/medien/*/intern", "/medien/2024/intern/lp.pdf", False),
        ("/lp.pdf$", "/lp.pdf", False),
        ("/lp.pdf$", "/lp.pdfx", True),
        ("/***a", "/xxa", False),
    ],
)
def test_a_star_matches_any_run_and_a_dollar_the_end(rule: str, path: str, allowed: bool) -> None:
    assert allows(f"User-agent: *\nDisallow: {rule}\n", path) is allowed


def test_an_empty_disallow_says_no_to_nothing() -> None:
    assert allows("User-agent: *\nDisallow:\n", "/lp.pdf")


def test_comments_spaces_case_and_a_byte_order_mark_are_read_through() -> None:
    text = "\ufeff  USER-AGENT : *   # alle\n\tdisallow:   /intern   # nicht\r\n"

    assert not allows(text, "/intern/lp.pdf")
    assert allows(text, "/lp.pdf")


def test_a_rule_before_any_robot_is_named_counts_for_none() -> None:
    assert allows("Disallow: /\nUser-agent: *\nDisallow: /intern\n", "/lp.pdf")


def test_a_path_with_letters_beyond_ascii_matches_however_it_is_spelled() -> None:
    text = "User-agent: *\nDisallow: /Lehrpläne/\n"

    assert not allows(text, "/Lehrpl%C3%A4ne/lp.pdf")
    assert not allows(text, "/Lehrpl%c3%a4ne/lp.pdf")
    assert not parse_robots("User-agent: *\nDisallow: /Lehrpl%c3%a4ne/\n", PRODUCT).allows(
        f"{SITE}/Lehrpläne/lp.pdf"
    )


def test_stars_without_end_match_in_no_time() -> None:
    # a regex of many stars backtracks without end on an address that does not match
    rule = "/" + "*a" * 40 + "b"
    started = time.perf_counter()

    assert allows(f"User-agent: *\nDisallow: {rule}\n", "/" + "a" * 1_900)
    assert time.perf_counter() - started < 1.0


def test_more_rules_than_are_matched_or_a_rule_too_long_forbid_everything() -> None:
    # what is not read is not taken to allow what it may forbid
    enough = "".join(f"Disallow: /a{number}\n" for number in range(MAX_RULES))
    too_many = enough + "Disallow: /b\n"
    too_long = "/" + "x" * MAX_RULE_SIGNS

    assert allows(f"User-agent: *\n{enough}", "/lp.pdf")
    assert not allows(f"User-agent: *\n{too_many}", "/lp.pdf")
    assert not allows(f"User-agent: *\nDisallow: {too_long}\n", "/lp.pdf")
    # another robot's long list is none of ours
    assert allows(f"User-agent: Googlebot\n{too_many}", "/lp.pdf")


def test_a_line_of_much_space_is_read_in_no_time() -> None:
    # a pattern that backtracked over the space took minutes on a line of 500 KiB
    spaces = " " * 400_000
    started = time.perf_counter()

    rules = parse_robots(f"User-agent:{spaces}*\nDisallow:{spaces}/intern{spaces}\n", PRODUCT)

    assert time.perf_counter() - started < 1.0
    assert not rules.allows(f"{SITE}/intern/lp.pdf")
    assert rules.allows(f"{SITE}/lp.pdf")


@pytest.mark.parametrize(
    ("rule", "path", "allowed"),
    [
        # RFC 9309 2.2.2: an unreserved sign matches however it is spelled
        ("/foo/bar/baz", "/foo/bar/%62%61%7A", False),
        ("/foo/bar/%62%61%7A", "/foo/bar/baz", False),
        ("/~lehrer/", "/%7Elehrer/lp.pdf", False),
        ("/%7elehrer/", "/~lehrer/lp.pdf", False),
        # a reserved one stays what it is: an encoded slash is no slash
        ("/a%2Fb", "/a/b", True),
        ("/a/b", "/a%2Fb", True),
        ("/foo/bar?baz=https%3A%2F%2Ffoo.bar", "/foo/bar?baz=https%3a%2f%2ffoo.bar", False),
    ],
)
def test_an_escape_is_compared_as_rfc_9309_says(rule: str, path: str, allowed: bool) -> None:
    assert allows(f"User-agent: *\nDisallow: {rule}\n", path) is allowed


def test_the_product_token_is_the_user_agent_s_first_word() -> None:
    assert product_token("Kompetenzkartierer-AI/1.0 (+https://example.org/bot)") == PRODUCT
    assert product_token("Kompetenzkartierer-AI (+https://example.org/bot)") == PRODUCT


# --- fetched


def mock(handler: Callable[[httpx2.Request], Any]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


def serving(status: int, body: bytes = b"") -> httpx2.MockTransport:
    return mock(lambda request: httpx2.Response(status, content=body))


@pytest.mark.anyio
async def test_a_robots_txt_found_gives_its_rules_asked_for_as_ourselves() -> None:
    asked: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request)
        return httpx2.Response(200, content=b"User-agent: *\nDisallow: /intern\n")

    rules = await read_robots(SITE, PRODUCT, transport=mock(handler), user_agent="Kompetenzkartierer-AI/1")

    assert str(asked[0].url) == f"{SITE}/robots.txt"
    assert asked[0].headers["user-agent"] == "Kompetenzkartierer-AI/1"
    assert not rules.allows(f"{SITE}/intern/lp.pdf")
    assert rules.allows(f"{SITE}/lp.pdf")


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404, 410])
async def test_a_robots_txt_not_there_for_us_sets_no_rules(status: int) -> None:
    # RFC 9309 2.3.1.3: unavailable (4xx) - any resource may be accessed
    rules = await read_robots(SITE, PRODUCT, transport=serving(status, b"User-agent: *\nDisallow: /\n"))

    assert rules.allows(f"{SITE}/lp.pdf")


@pytest.mark.anyio
@pytest.mark.parametrize("status", [429, 500, 503])
async def test_a_host_that_asks_to_wait_or_fails_waits_for_a_later_check(status: int) -> None:
    with pytest.raises(HostDeferred) as deferred:
        await read_robots(SITE, PRODUCT, transport=serving(status))

    assert deferred.value.status == status


@pytest.mark.anyio
async def test_a_host_that_does_not_answer_waits_for_a_later_check() -> None:
    def refusing(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    async def late(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200)

    for transport in (mock(refusing), mock(late)):
        with pytest.raises(HostDeferred) as deferred:
            await read_robots(SITE, PRODUCT, transport=transport, total_timeout=0.1)
        assert deferred.value.status is None


@pytest.mark.anyio
async def test_robots_txt_is_followed_through_five_redirects_and_past_them_is_none() -> None:
    def redirecting(hops: int) -> httpx2.MockTransport:
        def handler(request: httpx2.Request) -> httpx2.Response:
            step = int(request.url.params.get("n", "0"))
            if step < hops:
                return httpx2.Response(301, headers={"location": f"/robots.txt?n={step + 1}"})
            return httpx2.Response(200, content=b"User-agent: *\nDisallow: /\n")

        return mock(handler)

    assert not (await read_robots(SITE, PRODUCT, transport=redirecting(5))).allows(f"{SITE}/lp.pdf")
    assert (await read_robots(SITE, PRODUCT, transport=redirecting(6))).allows(f"{SITE}/lp.pdf")


@pytest.mark.anyio
async def test_the_rules_of_a_robots_txt_past_500_kib_are_its_first_500_kib() -> None:
    body = b"User-agent: *\nDisallow: /intern\n" + b"# " + b"x" * ROBOTS_BYTES + b"\nDisallow: /\n"
    # in the chunks the network hands over: a body built from bytes arrives in one piece
    streaming = mock(lambda request: httpx2.Response(200, content=arriving(in_chunks(body))))

    rules = await read_robots(SITE, PRODUCT, transport=streaming)

    assert not rules.allows(f"{SITE}/intern/lp.pdf")
    assert rules.allows(f"{SITE}/lp.pdf")


@pytest.mark.anyio
async def test_a_line_cut_at_500_kib_counts_for_nothing() -> None:
    # "Allow: /intern/geheim/oeffentlich" cut to "Allow: /intern/ge" allowed /intern/gesperrt/
    start = b"User-agent: *\nDisallow: /intern/\n#"
    head = start + b"x" * (ROBOTS_BYTES - len("Allow: /intern/ge") - len(start) - 1) + b"\n"
    body = head + b"Allow: /intern/geheim/oeffentlich\n"
    streaming = mock(lambda request: httpx2.Response(200, content=arriving(in_chunks(body, 1000))))

    rules = await read_robots(SITE, PRODUCT, transport=streaming)

    assert not rules.allows(f"{SITE}/intern/gesperrt/lp.pdf")


@pytest.mark.anyio
async def test_robots_txt_is_read_no_further_than_its_rules_count() -> None:
    handed: list[bytes] = []

    async def body() -> AsyncIterator[bytes]:
        for chunk in in_chunks(b"User-agent: *\nDisallow: /intern\n" + b"#" * (4 * MIB)):
            handed.append(chunk)
            yield chunk

    await read_robots(SITE, PRODUCT, transport=mock(lambda request: httpx2.Response(200, content=body())))

    assert len(handed) <= ROBOTS_BYTES // CHUNK + 2


@pytest.mark.anyio
async def test_a_robots_txt_there_but_unreadable_waits_for_a_later_check() -> None:
    # it has rules we cannot read: no rules is no answer to that (RFC 9309 2.3.1.3: only 4xx)
    def packed_unknown(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"\x00\x01", headers={"content-encoding": "br"})

    with pytest.raises(HostDeferred):
        await read_robots(SITE, PRODUCT, transport=mock(packed_unknown))


@pytest.mark.anyio
async def test_a_robots_txt_led_somewhere_not_to_be_asked_waits_for_a_later_check() -> None:
    # the host itself is public: its addresses are no unreachable ones for that
    def away(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(301, headers={"location": "ftp://files.example/robots.txt"})

    with pytest.raises(HostDeferred):
        await read_robots(SITE, PRODUCT, transport=mock(away))


@pytest.mark.anyio
async def test_a_host_not_to_be_asked_at_all_is_refused_as_such() -> None:
    # without a transport: the pinned one, which refuses a literal inside the network
    with pytest.raises(UrlNotAllowed):
        await read_robots("http://127.0.0.1", PRODUCT)


@pytest.mark.anyio
async def test_robots_txt_is_asked_for_without_a_trace_of_ours() -> None:
    asked: list[httpx2.Headers] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request.headers)
        return httpx2.Response(404)

    take_trace_headers([(b"x-client-trace-id", b"trace-of-the-check")], "request-1")
    await read_robots(SITE, PRODUCT, transport=mock(handler))

    assert "x-client-trace-id" not in asked[0]
