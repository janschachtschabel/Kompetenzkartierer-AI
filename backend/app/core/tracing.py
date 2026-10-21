"""The trace headers of a request, named in its log lines and sent on with the calls it makes.

The platform traces in the B3 format and passes ``x-client-trace-id`` from service to service,
so the logs of all services can be filtered for one request. The values are caller input: one
with signs no trace id has, or longer than a log line should hold, is dropped, not changed - a
changed trace id joins nothing. Ported from compendious-text-fastapi (D108).
"""

import re
from collections.abc import Iterable
from contextvars import ContextVar

REQUEST_ID = "X-Request-ID"
CLIENT_TRACE = "x-client-trace-id"
B3_TRACE = "x-b3-traceid"
B3_SINGLE = "b3"
TRACE_PARENT = "traceparent"
TRACE_STATE = "tracestate"
# B3 in its multi-header and single-header form, W3C trace context, the client's trace id
TRACE_HEADERS = frozenset(
    {
        CLIENT_TRACE,
        B3_TRACE,
        "x-b3-spanid",
        "x-b3-parentspanid",
        "x-b3-sampled",
        "x-b3-flags",
        B3_SINGLE,
        TRACE_PARENT,
        TRACE_STATE,
    }
)
MAX_TRACE_CHARS = 256  # a B3 header holds some 70 signs, a client's trace id fewer
MAX_STATE_CHARS = 512  # W3C: vendors should pass on at least 512 signs of tracestate
_TRACE_VALUE = re.compile("[A-Za-z0-9._:@+/=,-]+")
# tracestate: visible ASCII and spaces (after a comma, as proxies join headers), no line end
_STATE_VALUE = re.compile("[ -~]+")
# A B3 trace id has 16 or 32 hex signs; "0", "1" and "d" alone are sampling decisions
_B3_ID = re.compile("[0-9a-f]{16}|[0-9a-f]{32}")

_trace: ContextVar[dict[str, str]] = ContextVar("trace_headers", default={})  # noqa: B039 - never mutated


def take_trace_headers(headers: Iterable[tuple[bytes, bytes]], request_id: str) -> dict[str, str]:
    """The harmless trace headers among a request's raw headers; they hold for the request.

    The first of a repeated header wins, except tracestate, whose repeats W3C joins.
    """
    found: dict[str, str] = {}
    for raw_name, raw_value in headers:
        name = raw_name.decode("latin-1").lower()
        if name not in TRACE_HEADERS or (name in found and name != TRACE_STATE):
            continue
        value = raw_value.decode("latin-1").strip()
        if name == TRACE_STATE:
            joined = f"{found[name]},{value}" if name in found else value
            if value and len(joined) <= MAX_STATE_CHARS and _STATE_VALUE.fullmatch(joined):
                found[name] = joined
        elif value and len(value) <= MAX_TRACE_CHARS and _TRACE_VALUE.fullmatch(value):
            found[name] = value
    _trace.set({**found, REQUEST_ID: request_id})
    return found


def trace_id() -> str | None:
    """The client's trace id, else the B3 one, else W3C's; ``None`` outside a traced request."""
    found = _trace.get()
    if found.get(CLIENT_TRACE):
        return found[CLIENT_TRACE]
    parent = found.get(TRACE_PARENT, "").split("-")
    candidates = (
        found.get(B3_TRACE, ""),
        found.get(B3_SINGLE, "").partition("-")[0],
        parent[1] if len(parent) >= 4 else "",
    )
    return next((candidate for candidate in candidates if _B3_ID.fullmatch(candidate)), None)


def outgoing_headers() -> dict[str, str]:
    """The trace headers and the request id a call made for the current request carries on."""
    return dict(_trace.get())
