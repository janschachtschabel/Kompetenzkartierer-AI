"""The HTTP requests one model call sent, answered or not (as the old app's extraction/llm.py).

pydantic-ai counts a request once it is answered (``RunUsage.requests``). A request that timed
out, lost its connection or was cancelled in flight was never answered, and the provider may still
have charged for it (old app, audit 2026-10-01, 7.9-2). The client ``build_model`` gives the SDK
counts each request into the ``Attempts`` of the call that sent it.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx2


class Attempts:
    """The requests sent within ``counted()``."""

    def __init__(self) -> None:
        self.sent = 0

    @contextmanager
    def counted(self) -> Iterator[None]:
        """Count what is sent inside the block: in this task, and in the tasks it starts, which
        copy the context and the counter with it. Calls side by side run in tasks of their own
        and count apart."""
        token = _ATTEMPTS.set(self)
        try:
            yield
        finally:
            _ATTEMPTS.reset(token)


_ATTEMPTS: ContextVar[Attempts | None] = ContextVar("kka_llm_attempts", default=None)
# What fails a request before a byte of it is written: no connection, none in time, none free in
# the pool. The client counts a request before it connects (httpx2 runs its hooks first)
_UNSENT = (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout)


def never_sent(error: BaseException) -> bool:
    """Whether ``error``, or one it was raised from or while handling - its chain as Python shows
    it - failed a request before it went out: the SDK and pydantic-ai wrap the client's error twice."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        if isinstance(current, _UNSENT):
            return True
        seen.add(id(current))
        if current.__cause__ is not None:
            current = current.__cause__
        else:
            current = None if current.__suppress_context__ else current.__context__
    return False


async def count_attempt(request: httpx2.Request) -> None:
    """The client's request hook: one more request of the call that sent it."""
    attempts = _ATTEMPTS.get()
    if attempts is not None:
        attempts.sent += 1
