"""One model call as the stages make it (plan M1 5.1, costs; after the old app's extraction/llm.py
and services/usage.py).

A stage's agent answers in its schema's form (``StructuredDict``, checked against the schema,
app/llm/schema.py) and asks again where the answer is out of form, twice at most. ``ask`` walks
the agent's run node by node: before each request it reserves the request's tokens - reckoned
input and the answer's cap - and after the answer it books what the answer reports, which takes
the reservation's place. A retry of the agent is a request like any other, reserved anew. A
refused request (an HTTP error) is booked as a request without tokens; one sent and never
answered - timed out, cut off, cancelled in flight - as its reservation, an estimate, since the
provider may have charged for it; so is an answer that reports no usage, and one no model could
read, which fails the call. A request that never went out (no connection) costs nothing. A 429,
a 5xx or a provider not reached is waited on and asked again, twice at most; the SDK does not
ask again on its own (app/llm/client.py).
"""

import asyncio
import logging
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

from app.core.metrics import observe_llm_request
from app.llm.attempts import Attempts, never_sent
from app.llm.metering import Meter, Spent, estimate_input
from app.llm.schema import schema_errors

log = logging.getLogger(__name__)

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
    """The output in the schema's form, or None where no answer took it - ``failure`` says why
    (out of form however often asked, an answer cut at the cap, a content filter); what the call
    spent."""

    output: dict[str, Any] | None
    spent: Spent
    failure: str | None = None


def build_agent(model: Model, *, schema: Mapping[str, Any], name: str, instructions: str) -> StageAgent:
    """The agent of a stage answering in ``schema``'s form, under the schema's ``name`` ("x4_aussagen").
    Every request of it reserves the cap its model sends (``max_tokens``, LLM_MAX_OUTPUT_TOKENS in
    app/llm/client.py); ValueError for a model that sends none - a request could cost anything."""
    if _NAME.fullmatch(name) is None:
        raise ValueError(f"{name!r}: a schema's name is letters, digits, _ and - (as OpenAI takes it)")
    output_tokens = (model.settings or {}).get("max_tokens")
    if output_tokens is None:
        raise ValueError("the stage's model sends no max_tokens: its answers would have no cap to reserve")
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
    only a rate limit or an outage is worth it, and never a spent quota (a 429 too); the
    provider's Retry-After where it gives one (``_wait``)."""
    if refused.status_code != 429 and refused.status_code < 500:
        return None
    if "insufficient_quota" in str(refused.body):
        return None
    return _wait(attempt, refused.retry_after)


def _wait(attempt: int, after: float | None = None) -> float | None:
    """The wait before asking again, twice at most: ``after``, else one that grows; spread a little,
    a minute at most."""
    if attempt >= _RETRIES_AFTER_REFUSAL:
        return None
    wait = after if after is not None else _WAIT_AFTER_REFUSAL * (attempt + 1)
    return min(wait * (1 + _SPREAD * _draw()), _LONGEST_WAIT)


async def ask(
    stage: StageAgent, content: str | Sequence[UserContent], *, meter: Meter, raw: RawSink | None = None
) -> Answer:
    """The stage's answer to ``content``, every request reserved and booked with ``meter`` and
    every answer kept in ``raw`` before it is checked. A request the provider was never reached
    with is asked again as a busy provider's is. BudgetExhausted where the budget holds no further
    request; ModelHTTPError where the provider refused for good; ModelAPIError where it was never
    reached; UnexpectedModelBehavior - or, on the Responses API, the library's own error - for an
    answer no model could read; whatever else failed. Each with the error it was raised from."""
    spent = Spent()
    attempt = 0
    while True:
        try:
            output, this, failure = await _attempt(stage, content, meter, raw)
            return Answer(output, spent + this, failure)
        except _Refused as refused:
            spent += refused.spent
            wait = wait_after(refused.error, attempt)
            if wait is None:
                raise refused.error from refused.error.__cause__
        except _NotSent as unsent:
            spent += unsent.spent
            wait = _wait(attempt)
            if wait is None:
                raise unsent.error from unsent.error.__cause__
        attempt += 1
        await _sleep(wait)


class _Refused(Exception):
    """A provider's refusal, with what the attempt spent up to it."""

    def __init__(self, error: ModelHTTPError, spent: Spent) -> None:
        self.error = error
        self.spent = spent


class _NotSent(Exception):
    """A request that never went out (``never_sent``), with what the attempt spent up to it."""

    def __init__(self, error: Exception, spent: Spent) -> None:
        self.error = error
        self.spent = spent


@dataclass
class _Open:
    """A request reserved and not yet booked: its input as reckoned, the requests sent before it,
    and what its answer reported once one came."""

    reservation: Any
    estimate: int
    sent_before: int
    answered: Spent | None = None


async def _attempt(
    stage: StageAgent, content: str | Sequence[UserContent], meter: Meter, raw: RawSink | None
) -> tuple[dict[str, Any] | None, Spent, str | None]:
    """One run of the agent, its requests reserved, answered and booked one by one: the output,
    what the run spent, and why there is no output where there is none."""
    spent = Spent()
    attempts = Attempts()
    open_: _Open | None = None
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
                        open_ = _Open(
                            await meter.reserve(estimate, stage.output_tokens), estimate, attempts.sent
                        )
                    elif Agent.is_call_tools_node(node) and open_ is not None:
                        open_.answered = _answered(node.model_response, open_.estimate, stage.output_tokens)
                        await meter.book(open_.reservation, open_.answered)
                        spent += open_.answered
                        open_ = None
                        # kept before the next node checks it against the schema
                        if raw is not None:
                            await raw.keep(ModelMessagesTypeAdapter.dump_json([node.model_response]))
                assert run.result is not None  # noqa: S101 - the run went to its end
                return run.result.output, spent, None
    except UnexpectedModelBehavior as error:
        if open_ is not None:  # raised by the request: an answer no model could read
            await _book_cut_off(meter, open_, stage, sent=attempts.sent > open_.sent_before)
            raise
        # every answer came and is booked: none took the schema's form, or the run stopped at one
        log.warning("a stage's answer took no form: %s", error.message)
        return None, spent, error.message
    except ModelHTTPError as error:
        # answered, with a refusal: nothing to charge but the request
        refused = Spent(requests=1)
        observe_llm_request("refused")
        if open_ is not None:
            await asyncio.shield(meter.book(open_.reservation, refused))
        raise _Refused(error, spent + refused) from error
    except BaseException as error:
        unsent = isinstance(error, Exception) and never_sent(error)
        if unsent:
            observe_llm_request("unsent")
        if open_ is not None:
            await _book_cut_off(meter, open_, stage, sent=attempts.sent > open_.sent_before and not unsent)
        if isinstance(error, Exception) and unsent:
            raise _NotSent(error, spent) from error
        raise


async def _book_cut_off(meter: Meter, open_: _Open, stage: StageAgent, *, sent: bool) -> None:
    """Book a request its run left unbooked: what its answer reported, where one came and its
    booking failed - the meter takes a reservation once - else what was held for it where it went
    out, the provider may have charged for it; nothing where it never did. Shielded: a cancel must
    not take the booking of a request that may be paid for along."""
    if open_.answered is not None:
        cost = open_.answered
    elif sent:
        observe_llm_request("unanswered", estimated_tokens=open_.estimate + stage.output_tokens)
        cost = Spent(
            input_tokens=open_.estimate,
            output_tokens=stage.output_tokens,
            unanswered_requests=1,
            estimated=True,
        )
    else:
        cost = Spent()
    await asyncio.shield(meter.book(open_.reservation, cost))


def _answered(response: ModelResponse, estimate: int, output_tokens: int) -> Spent:
    """What an answer cost, as it reports it - or, where it reports no input at all (a gateway that
    counts nothing), what was held for it, as an estimate; counted."""
    usage = response.usage
    if usage.input_tokens == 0:
        observe_llm_request("answered", estimated_tokens=estimate + output_tokens)
        return Spent(input_tokens=estimate, output_tokens=output_tokens, requests=1, estimated=True)
    observe_llm_request(
        "answered",
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cache_read_tokens,
        output_tokens=usage.output_tokens,
    )
    return Spent(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cache_read_tokens,
        output_tokens=usage.output_tokens,
        requests=1,
    )
