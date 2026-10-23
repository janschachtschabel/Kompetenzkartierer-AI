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
from pydantic_ai.usage import RunUsage


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

    def unanswered(self, spent: RunUsage | None) -> int:
        """The requests sent and never answered, given what pydantic-ai counted of the call: an
        answered request is one request sent, as the app neither streams nor polls. Zero for a
        model that sends nothing over the client, as a test's does."""
        return max(self.sent - (spent.requests if spent is not None else 0), 0)


_ATTEMPTS: ContextVar[Attempts | None] = ContextVar("kka_llm_attempts", default=None)


async def count_attempt(request: httpx2.Request) -> None:
    """The client's request hook: one more request of the call that sent it."""
    attempts = _ATTEMPTS.get()
    if attempts is not None:
        attempts.sent += 1
