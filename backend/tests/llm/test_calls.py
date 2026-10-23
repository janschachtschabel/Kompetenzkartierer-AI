"""One model call as the stages make it (plan M1 5.1): checked against its schema, reserved before
each request and booked after it, waited on after a 429 or a 5xx - and its answers kept before
anybody reads them."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import CachePoint, ModelMessage, ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from app.llm import calls
from app.llm.calls import StageAgent, ask, breakpoint_settings, build_agent, cached_up_to, wait_after
from app.llm.client import build_model
from app.llm.metering import BudgetExhausted, Spent
from tests.llm.test_client import llm_settings

pytestmark = pytest.mark.anyio

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title"],
    "properties": {"title": {"type": "string"}},
}
USAGE = RequestUsage(input_tokens=100, cache_read_tokens=40, output_tokens=20)


class Ledger:
    """A meter in place of the database: keeps what it was asked, refuses past ``holds`` requests."""

    def __init__(self, holds: int | None = None) -> None:
        self.holds = holds
        self.reserved: list[tuple[int, int]] = []
        self.booked: list[tuple[int, Spent]] = []

    async def reserve(self, input_tokens: int, output_tokens: int) -> int:
        if self.holds is not None and len(self.reserved) >= self.holds:
            raise BudgetExhausted("the budget is spent")
        self.reserved.append((input_tokens, output_tokens))
        return len(self.reserved)

    async def book(self, reservation: int, spent: Spent) -> None:
        self.booked.append((reservation, spent))


class Kept:
    """Raw answers kept, in their order."""

    def __init__(self) -> None:
        self.answers: list[bytes] = []

    async def keep(self, data: bytes) -> str:
        self.answers.append(data)
        return f"runs/r/x4/{len(self.answers)}.json"


def stage(answers: list[str], *, output_tokens: int = 2_000) -> tuple[StageAgent, list[list[ModelMessage]]]:
    """A stage over a model that answers ``answers`` in turn, as the tool call of its output."""
    seen: list[list[ModelMessage]] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(messages)
        args = answers[min(len(seen), len(answers)) - 1]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)], usage=USAGE)

    built = build_agent(
        FunctionModel(answer, settings={"max_tokens": output_tokens}),
        schema=SCHEMA,
        name="titel",
        instructions="Nenne den Titel.",
    )
    return built, seen


async def test_an_answer_of_the_schema_s_form_is_reserved_before_and_booked_after() -> None:
    built, _ = stage(['{"title": "Zahlen"}'])
    ledger, kept = Ledger(), Kept()

    answer = await ask(built, "Das Dokument.", meter=ledger, raw=kept)

    assert answer.output == {"title": "Zahlen"}
    [(estimate, cap)] = ledger.reserved
    assert estimate > 0 and cap == 2_000
    assert ledger.booked == [
        (1, Spent(input_tokens=100, cached_input_tokens=40, output_tokens=20, requests=1))
    ]
    assert answer.spent == ledger.booked[0][1]
    [raw] = kept.answers
    assert json.loads(raw)[0]["usage"]["input_tokens"] == 100  # the answer with its usage, as it came


async def test_an_answer_out_of_form_is_asked_again_each_time_reserved_anew() -> None:
    built, seen = stage(['{"title": 3}', '{"title": "Zahlen"}'])
    ledger, kept = Ledger(), Kept()

    answer = await ask(built, "Das Dokument.", meter=ledger, raw=kept)

    assert answer.output == {"title": "Zahlen"}
    assert (len(ledger.reserved), len(ledger.booked), len(kept.answers)) == (2, 2, 2)
    assert ledger.reserved[1][0] > ledger.reserved[0][0]  # the retry replays the first answer
    retry = [part for part in seen[1][-1].parts if isinstance(part, RetryPromptPart)]
    assert retry and "$.title: a string" in str(retry[0].content)
    assert answer.spent.requests == 2


async def test_an_answer_never_in_form_gives_none_and_books_every_request() -> None:
    built, _ = stage(['{"title": 3}'])
    ledger = Ledger()

    answer = await ask(built, "Das Dokument.", meter=ledger)

    assert answer.output is None
    assert len(ledger.reserved) == len(ledger.booked) == 3  # the answer and two retries
    assert answer.spent.requests == 3


async def test_a_budget_that_holds_no_more_stops_the_call_before_the_request() -> None:
    built, seen = stage(['{"title": 3}', '{"title": "Zahlen"}'])
    ledger = Ledger(holds=1)

    with pytest.raises(BudgetExhausted):
        await ask(built, "Das Dokument.", meter=ledger)

    assert (len(seen), len(ledger.booked)) == (1, 1)  # the first was asked and booked, the retry never


def gateway(handler: Callable[[httpx2.Request], Any]) -> StageAgent:
    model = build_model(
        llm_settings(llm_provider="openai-compatible", llm_max_output_tokens=2_000),
        transport=httpx2.MockTransport(handler),
    )
    return build_agent(model, schema=SCHEMA, name="titel", instructions="Nenne den Titel.")


def completion(
    title: str, *, prompt: int = 120, cached: int = 100, completion_tokens: int = 30
) -> dict[str, Any]:
    call = {
        "id": "t1",
        "type": "function",
        "function": {"name": "final_result", "arguments": json.dumps({"title": title})},
    }
    return {
        "id": "c1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-6-luna",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": [call]},
            }
        ],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt + completion_tokens,
            "prompt_tokens_details": {"cached_tokens": cached},
        },
    }


async def test_a_gateway_s_answer_is_booked_with_the_usage_it_reports() -> None:
    ledger = Ledger()

    answer = await ask(
        gateway(lambda _: httpx2.Response(200, json=completion("Zahlen"))), "Text", meter=ledger
    )

    assert answer.output == {"title": "Zahlen"}
    assert ledger.booked == [
        (1, Spent(input_tokens=120, cached_input_tokens=100, output_tokens=30, requests=1))
    ]


async def test_a_refused_request_costs_no_tokens_but_is_booked_as_a_request() -> None:
    ledger = Ledger()
    refusal = {"error": {"message": "bad", "type": "invalid_request_error"}}

    with pytest.raises(ModelHTTPError):
        await ask(gateway(lambda _: httpx2.Response(400, json=refusal)), "Text", meter=ledger)

    assert ledger.booked == [(1, Spent(requests=1))]


async def test_a_request_never_answered_books_its_reservation_as_an_estimate() -> None:
    ledger = Ledger()

    def timed_out(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("no answer", request=request)

    with pytest.raises(ModelAPIError, match="timed out"):
        await ask(gateway(timed_out), "Text", meter=ledger)

    [(estimate, cap)] = ledger.reserved
    assert ledger.booked == [
        (1, Spent(input_tokens=estimate, output_tokens=cap, unanswered_requests=1, estimated=True))
    ]


async def test_a_call_cancelled_in_flight_books_its_reservation_as_an_estimate() -> None:
    ledger = Ledger()
    sent = asyncio.Event()

    async def hanging(request: httpx2.Request) -> httpx2.Response:
        sent.set()
        await asyncio.Event().wait()
        raise AssertionError("never answered")

    task = asyncio.create_task(ask(gateway(hanging), "Text", meter=ledger))
    await sent.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    [(estimate, cap)] = ledger.reserved
    assert ledger.booked == [
        (1, Spent(input_tokens=estimate, output_tokens=cap, unanswered_requests=1, estimated=True))
    ]


@pytest.fixture
def waited(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(calls, "_sleep", sleep)
    monkeypatch.setattr(calls, "_draw", lambda: 0.0)
    return slept


def answers(*replies: httpx2.Response) -> Callable[[httpx2.Request], httpx2.Response]:
    queue = list(replies)
    return lambda _: queue.pop(0)


BUSY = {"error": {"message": "busy", "type": "server_error"}}


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_a_busy_provider_is_waited_on_and_asked_again_with_a_new_reservation(
    waited: list[float], status: int
) -> None:
    ledger = Ledger()
    replies = answers(httpx2.Response(status, json=BUSY), httpx2.Response(200, json=completion("Zahlen")))

    answer = await ask(gateway(replies), "Text", meter=ledger)

    assert answer.output == {"title": "Zahlen"}
    assert waited == [20.0]
    assert [spent for _, spent in ledger.booked] == [
        Spent(requests=1),
        Spent(input_tokens=120, cached_input_tokens=100, output_tokens=30, requests=1),
    ]
    assert answer.spent.requests == 2


async def test_a_busy_provider_s_retry_after_sets_the_wait(waited: list[float]) -> None:
    replies = answers(
        httpx2.Response(429, json=BUSY, headers={"retry-after": "7"}),
        httpx2.Response(200, json=completion("Zahlen")),
    )

    await ask(gateway(replies), "Text", meter=Ledger())

    assert waited == [7.0]


async def test_a_provider_busy_three_times_fails_the_call(waited: list[float]) -> None:
    ledger = Ledger()

    with pytest.raises(ModelHTTPError):
        await ask(gateway(lambda _: httpx2.Response(503, json=BUSY)), "Text", meter=ledger)

    assert (waited, len(ledger.booked)) == ([20.0, 40.0], 3)


async def test_a_spent_quota_at_the_provider_is_not_waited_on(waited: list[float]) -> None:
    quota = {
        "error": {
            "message": "You exceeded your current quota",
            "type": "insufficient_quota",
            "code": "insufficient_quota",
        }
    }

    with pytest.raises(ModelHTTPError):
        await ask(gateway(lambda _: httpx2.Response(429, json=quota)), "Text", meter=Ledger())

    assert waited == []


def refusal(status: int, retry_after: str | None = None, code: str | None = None) -> ModelHTTPError:
    body = {"error": {"message": "x", "type": "server_error", "code": code}} if code else BUSY
    headers = {"retry-after": retry_after} if retry_after else {}
    return ModelHTTPError(status, "gpt-6-luna", body=body, headers=headers)


@pytest.mark.parametrize(
    ("refused", "attempt", "draw", "wait"),
    [
        (refusal(429), 0, 0.0, 20.0),
        (refusal(500), 1, 0.0, 40.0),
        (refusal(503), 0, 1.0, 25.0),  # spread by up to a quarter
        (refusal(429, retry_after="300"), 0, 0.0, 60.0),  # never longer than a minute
        (refusal(429), 2, 0.0, None),  # asked three times
        (refusal(400), 0, 0.0, None),
        (refusal(429, code="insufficient_quota"), 0, 0.0, None),
    ],
)
def test_the_wait_after_a_refusal(
    monkeypatch: pytest.MonkeyPatch, refused: ModelHTTPError, attempt: int, draw: float, wait: float | None
) -> None:
    monkeypatch.setattr(calls, "_draw", lambda: draw)

    assert wait_after(refused, attempt) == wait


def test_a_prompt_caches_its_shared_opening_behind_a_breakpoint_where_the_model_takes_one() -> None:
    responses = build_model(llm_settings())
    chat = build_model(llm_settings(llm_provider="openai-compatible"))

    content = cached_up_to("Dokument\n", "Auftrag", responses)

    assert content == ["Dokument\n", CachePoint(), "Auftrag"]
    assert breakpoint_settings(content) == {"openai_prompt_cache_options": {"mode": "explicit"}}
    assert cached_up_to("Dokument\n", "Auftrag", chat) == "Dokument\nAuftrag"  # a gateway may not know it
    assert breakpoint_settings("Dokument\nAuftrag") is None


async def test_a_call_with_a_breakpoint_sends_it_behind_the_shared_opening() -> None:
    body: dict[str, Any] = {}

    def read(request: httpx2.Request) -> httpx2.Response:
        body.update(json.loads(request.content))
        return httpx2.Response(400, json={"error": {"message": "read", "type": "invalid_request_error"}})

    model = build_model(llm_settings(), transport=httpx2.MockTransport(read))
    built = build_agent(model, schema=SCHEMA, name="titel", instructions="Nenne den Titel.")

    with pytest.raises(ModelHTTPError):
        await ask(built, cached_up_to("Dokument\n", "Auftrag", model), meter=Ledger())

    shared, own = body["input"][-1]["content"]
    assert shared["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert "prompt_cache_breakpoint" not in own
    assert body["prompt_cache_options"] == {"mode": "explicit"}


def test_a_stage_takes_its_schema_s_name_as_openai_does() -> None:
    with pytest.raises(ValueError, match="name"):
        build_agent(
            FunctionModel(lambda *_: ModelResponse(parts=[]), settings={"max_tokens": 1_000}),
            schema=SCHEMA,
            name="x 4",
            instructions="",
        )
    assert isinstance(stage(['{"title": "a"}'])[0].agent, Agent)


def test_a_stage_reserves_the_cap_its_model_sends() -> None:
    # a cap of the stage's own could hold less than a request of its model may cost
    model = build_model(llm_settings(llm_max_output_tokens=4_321))

    built = build_agent(model, schema=SCHEMA, name="titel", instructions="Nenne den Titel.")

    assert built.output_tokens == 4_321


def test_a_stage_needs_a_model_that_caps_its_answers() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        build_agent(
            FunctionModel(lambda *_: ModelResponse(parts=[])), schema=SCHEMA, name="titel", instructions=""
        )
