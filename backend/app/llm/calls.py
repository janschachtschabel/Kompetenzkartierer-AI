"""One model call as the stages make it (plan M1 5.1, costs; after the old app's extraction/llm.py
and services/usage.py).

A stage's agent answers in its schema's form (``StructuredDict``, checked against the schema,
app/llm/schema.py) and asks again where the answer is out of form, twice at most. ``ask`` walks
the agent's run node by node: before each request it reserves the request's tokens - reckoned
input and the answer's cap - and after the answer it books what the answer reports, which takes
the reservation's place. A retry of the agent is a request like any other, reserved anew. A
refused request (an HTTP error) is booked as a request without tokens; one sent and never
answered - timed out, cut off, cancelled in flight - as its reservation, an estimate, since the
provider may have charged for it. A 429 or a 5xx is waited on and asked again, twice at most;
the SDK does not ask again on its own (app/llm/client.py).
"""

import asyncio
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import CachePoint, ModelMessagesTypeAdapter, ModelResponse, UserContent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModelSettings
from pydantic_ai.output import StructuredDict

from app.llm.attempts import Attempts
from app.llm.metering import Meter, Spent, estimate_input
from app.llm.schema import schema_errors

# A stage's answer out of form is asked again this often, each a request of its own
OUTPUT_RETRIES = 2
# A rate limit or an outage is waited on this often (old app, pipeline.py)
_RETRIES_AFTER_REFUSAL = 2
_WAIT_AFTER_REFUSAL = 20.0
_LONGEST_WAIT = 60.0
_SPREAD = 0.25
_sleep = asyncio.sleep
_draw = random.random
# as OpenAI names a function or a schema
_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")


class RawSink(Protocol):
    """Where a call's answers are kept as they came (app/llm/raw.py)."""

    async def keep(self, data: bytes) -> str: ...


@dataclass(frozen=True)
class StageAgent:
    """A stage's agent with what its calls reckon on: the schema, the instructions, the cap."""

    agent: Agent[None, dict[str, Any]]
    schema: Mapping[str, Any]
    instructions: str
    output_tokens: int


@dataclass(frozen=True)
class Answer:
    """The output in the schema's form, or None where no answer took it; what the call spent."""

    output: dict[str, Any] | None
    spent: Spent


def build_agent(
    model: Model, *, schema: Mapping[str, Any], name: str, instructions: str, output_tokens: int
) -> StageAgent:
    """The agent of a stage answering in ``schema``'s form, under the schema's ``name`` ("x4_aussagen");
    ``output_tokens`` is the cap every request of it reserves (LLM_MAX_OUTPUT_TOKENS)."""
    if _NAME.fullmatch(name) is None:
        raise ValueError(f"{name!r}: a schema's name is letters, digits, _ and - (as OpenAI takes it)")
    agent: Agent[None, dict[str, Any]] = Agent(
        model,
        output_type=StructuredDict(dict(schema), name=name),
        instructions=instructions,
        retries=OUTPUT_RETRIES,
    )

    @agent.output_validator
    def in_form(output: dict[str, Any]) -> dict[str, Any]:
        errors = schema_errors(schema, output)
        if errors:
            raise ModelRetry("The answer is out of the schema's form:\n" + "\n".join(errors))
        return output

    return StageAgent(agent, schema, instructions, output_tokens)


def cached_up_to(shared: str, own: str, model: Model) -> str | list[UserContent]:
    """A prompt whose opening every call of a series sends alike: ``shared`` and ``own`` with a
    cache breakpoint between them where the model takes one. The old app measured it: without
    one, gpt-6-luna cached behind the task, which differs per call, and read 2.3 % of its input
    from the cache. Never on Chat Completions: a gateway may not know the field, and answers it
    with a 400 halfway through a paid run."""
    takes = not isinstance(model, OpenAIChatModel) and bool(
        model.profile.get("openai_supports_prompt_cache_breakpoints", False)
    )
    return [shared, CachePoint(), own] if takes else shared + own


def breakpoint_settings(content: str | Sequence[UserContent]) -> OpenAIResponsesModelSettings | None:
    """The explicit cache mode for content with a breakpoint, so the cache keeps the opening
    alone; None otherwise, where the mode would cache nothing at all."""
    if isinstance(content, str) or not any(isinstance(item, CachePoint) for item in content):
        return None
    return OpenAIResponsesModelSettings(openai_prompt_cache_options={"mode": "explicit"})


def wait_after(refused: ModelHTTPError, attempt: int) -> float | None:
    """How long to wait before asking again after the provider refused, or None when not to:
    only a rate limit or an outage is worth it, twice at most, and never a spent quota (a 429
    too). The provider's Retry-After, else a wait that grows; spread a little, a minute at most."""
    if attempt >= _RETRIES_AFTER_REFUSAL:
        return None
    if refused.status_code != 429 and refused.status_code < 500:
        return None
    if "insufficient_quota" in str(refused.body):
        return None
    after = refused.retry_after
    wait = after if after is not None else _WAIT_AFTER_REFUSAL * (attempt + 1)
    return min(wait * (1 + _SPREAD * _draw()), _LONGEST_WAIT)


async def ask(
    stage: StageAgent, content: str | Sequence[UserContent], *, meter: Meter, raw: RawSink | None = None
) -> Answer:
    """The stage's answer to ``content``, every request reserved and booked with ``meter`` and
    every answer kept in ``raw`` before it is checked. BudgetExhausted where the budget holds no
    further request; ModelHTTPError where the provider refused for good; whatever else failed."""
    spent = Spent()
    attempt = 0
    while True:
        try:
            output, this = await _attempt(stage, content, meter, raw)
            return Answer(output, spent + this)
        except _Refused as refused:
            spent += refused.spent
            wait = wait_after(refused.error, attempt)
            if wait is None:
                raise refused.error from None
            attempt += 1
            await _sleep(wait)


class _Refused(Exception):
    """A provider's refusal, with what the attempt spent up to it."""

    def __init__(self, error: ModelHTTPError, spent: Spent) -> None:
        self.error = error
        self.spent = spent


async def _attempt(
    stage: StageAgent, content: str | Sequence[UserContent], meter: Meter, raw: RawSink | None
) -> tuple[dict[str, Any] | None, Spent]:
    """One run of the agent: its requests reserved, answered and booked one by one."""
    spent = Spent()
    attempts = Attempts()
    open_: tuple[Any, int, int] | None = None  # reservation, its input, the requests sent before it
    output: dict[str, Any] | None = None
    try:
        with attempts.counted():
            async with stage.agent.iter(content, model_settings=breakpoint_settings(content)) as run:
                async for node in run:
                    if Agent.is_model_request_node(node):
                        estimate = estimate_input(
                            run.all_messages(),
                            node.request,
                            instructions=stage.instructions,
                            schema=stage.schema,
                        )
                        open_ = (await meter.reserve(estimate, stage.output_tokens), estimate, attempts.sent)
                    elif Agent.is_call_tools_node(node) and open_ is not None:
                        answered = _answered(node.model_response)
                        if raw is not None:
                            await raw.keep(ModelMessagesTypeAdapter.dump_json([node.model_response]))
                        await meter.book(open_[0], answered)
                        spent += answered
                        open_ = None
                assert run.result is not None  # noqa: S101 - the run went to its end
                output = run.result.output
    except UnexpectedModelBehavior:
        output = None  # out of form however often asked: every answer is booked already
    except ModelHTTPError as error:
        # answered, with a refusal: nothing to charge but the request
        refused = Spent(requests=1)
        if open_ is not None:
            await asyncio.shield(meter.book(open_[0], refused))
        raise _Refused(error, spent + refused) from error
    except BaseException:
        if open_ is not None:
            reservation, estimate, before = open_
            sent = attempts.sent > before
            unanswered = (
                Spent(
                    input_tokens=estimate,
                    output_tokens=stage.output_tokens,
                    unanswered_requests=1,
                    estimated=True,
                )
                if sent
                else Spent()
            )
            # shielded: a cancel must not take the booking of a request that may be paid for along
            await asyncio.shield(meter.book(reservation, unanswered))
        raise
    return output, spent


def _answered(response: ModelResponse) -> Spent:
    usage = response.usage
    return Spent(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cache_read_tokens,
        output_tokens=usage.output_tokens,
        requests=1,
    )
