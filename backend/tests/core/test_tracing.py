"""Trace headers of a request: taken when harmless, dropped otherwise, sent on with its calls."""

import contextvars
from collections.abc import Callable

import pytest

from app.core.tracing import outgoing_headers, take_trace_headers, trace_id

B3_ID = "463ac35c9f6413ad48485a3953bb6124"
B3_SPAN = "a2fb4a1d1a96d312"
W3C_ID = "0af7651916cd43dd8448eb211c80319c"


def raw(*pairs: tuple[str, str]) -> list[tuple[bytes, bytes]]:
    return [(name.encode("latin-1"), value.encode("latin-1")) for name, value in pairs]


def isolated[T](call: Callable[[], T]) -> T:
    """Runs ``call`` in a copy of the context, as a request does: nothing leaks into the next test."""
    return contextvars.copy_context().run(call)


def traced(*pairs: tuple[str, str], request_id: str = "req-1") -> str | None:
    def run() -> str | None:
        take_trace_headers(raw(*pairs), request_id)
        return trace_id()

    return isolated(run)


def test_outside_a_request_there_is_no_trace() -> None:
    assert isolated(trace_id) is None
    assert isolated(outgoing_headers) == {}


def test_the_client_trace_id_names_the_trace_before_b3() -> None:
    assert traced(("x-client-trace-id", "client-42"), ("x-b3-traceid", B3_ID)) == "client-42"


@pytest.mark.parametrize(
    "pairs",
    [
        (("X-B3-TraceId", B3_ID),),
        (("b3", f"{B3_ID}-{B3_SPAN}-1"),),
        (("traceparent", f"00-{B3_ID}-{B3_SPAN}-01"),),
    ],
    ids=["b3-multi", "b3-single", "w3c"],
)
def test_the_trace_id_is_read_from_b3_or_w3c(pairs: tuple[tuple[str, str], ...]) -> None:
    assert traced(*pairs) == B3_ID


def test_b3_comes_before_w3c() -> None:
    assert traced(("traceparent", f"00-{W3C_ID}-{B3_SPAN}-01"), ("x-b3-traceid", B3_ID)) == B3_ID


@pytest.mark.parametrize("decision", ["0", "1", "d"])
def test_a_sampling_decision_alone_is_no_trace(decision: str) -> None:
    assert traced(("b3", decision)) is None


@pytest.mark.parametrize(
    "value",
    ["with space", "line\nbreak", "esc\x1b[31m", "x" * 257, ""],
    ids=["space", "newline", "escape", "too-long", "empty"],
)
def test_a_value_no_trace_id_has_is_dropped_not_changed(value: str) -> None:
    def run() -> dict[str, str]:
        return take_trace_headers(raw(("x-client-trace-id", value)), "req-1")

    assert isolated(run) == {}


def test_the_first_of_repeated_headers_wins() -> None:
    assert traced(("x-client-trace-id", "first"), ("x-client-trace-id", "second")) == "first"


def test_repeated_tracestate_headers_are_joined_and_bounded() -> None:
    def run(*values: str) -> dict[str, str]:
        return take_trace_headers(raw(*(("tracestate", value) for value in values)), "req-1")

    assert isolated(lambda: run("a=1", "b=2")) == {"tracestate": "a=1,b=2"}
    assert isolated(lambda: run("a=" + "x" * 300, "b=" + "y" * 300)) == {"tracestate": "a=" + "x" * 300}


def test_other_headers_are_not_trace_headers() -> None:
    def run() -> dict[str, str]:
        return take_trace_headers(raw(("authorization", "Bearer secret"), ("cookie", "s=1")), "req-1")

    assert isolated(run) == {}


def test_outgoing_headers_carry_the_trace_and_the_request_id() -> None:
    def run() -> dict[str, str]:
        take_trace_headers(raw(("x-b3-traceid", B3_ID), ("x-b3-spanid", B3_SPAN)), "req-7")
        return outgoing_headers()

    assert isolated(run) == {"x-b3-traceid": B3_ID, "x-b3-spanid": B3_SPAN, "X-Request-ID": "req-7"}
