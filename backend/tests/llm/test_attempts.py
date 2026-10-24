"""The requests a model call sent, whether or not they were answered (plan M1 5.1): pydantic-ai
counts a request once it is answered, and a request that timed out or was cancelled in flight may
still be paid for (old app, audit 2026-10-01)."""

import asyncio

import httpx2
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

from app.llm.attempts import Attempts, never_sent
from app.llm.client import build_model
from tests.llm.test_client import Recorder, llm_settings

pytestmark = pytest.mark.anyio


def agent() -> tuple[Recorder, Agent[None, str]]:
    recorder = Recorder()
    return recorder, Agent(build_model(llm_settings(), transport=httpx2.MockTransport(recorder)))


async def refused(agent: Agent[None, str]) -> None:
    with pytest.raises(ModelHTTPError):
        await agent.run("Nenne ein Thema.")


async def test_a_call_counts_each_request_it_sends_and_in_the_tasks_it_starts() -> None:
    recorder, model = agent()
    attempts = Attempts()

    with attempts.counted():
        await refused(model)
        await asyncio.gather(refused(model), refused(model))

    assert attempts.sent == len(recorder.requests) == 3


async def test_calls_side_by_side_count_apart_and_none_outside_counts() -> None:
    recorder, model = agent()
    first, second = Attempts(), Attempts()

    async def counted(attempts: Attempts, times: int) -> None:
        with attempts.counted():
            for _ in range(times):
                await refused(model)

    await asyncio.gather(counted(first, 1), counted(second, 2))
    await refused(model)  # counted by nobody

    assert (first.sent, second.sent, len(recorder.requests)) == (1, 2, 4)


def test_a_request_failed_in_connecting_is_told_by_its_chain_as_python_shows_it() -> None:
    def raised(how: str) -> BaseException:
        try:
            try:
                raise httpx2.ConnectError("refused")
            except httpx2.ConnectError as connect:
                if how == "from":
                    raise RuntimeError("wrapped") from connect
                if how == "during":
                    raise RuntimeError("wrapped")  # noqa: B904 - the implicit chain is what is tried
                raise RuntimeError("anew") from None
        except RuntimeError as error:
            return error
        raise AssertionError("nothing raised")

    assert never_sent(raised("from"))
    assert never_sent(raised("during"))
    assert not never_sent(raised("none"))  # the chain Python shows ends at the error itself
