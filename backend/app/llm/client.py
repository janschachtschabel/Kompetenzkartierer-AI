"""The configured language model, as pydantic-ai models it (after the old app's extraction/llm.py).

``openai`` is spoken to over the Responses API, which carries reasoning effort and text
verbosity; ``openai-compatible`` over Chat Completions, which carries the effort. Every request
caps its answer at LLM_MAX_OUTPUT_TOKENS, is counted into the call that sent it
(app/llm/attempts.py), carries the trace of its request or job, and is sent once: the SDK does
not ask again on its own. No network call happens here: the client connects on the first
request, so the app starts without the provider. pydantic-ai 2.42 does not know gpt-6-luna and
would silently drop its prompt cache breakpoint and encrypted reasoning; the model is described
as it was measured instead.
"""

import re
from typing import Any, cast

import httpx2
from openai import AsyncOpenAI
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIChatModelSettings,
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.profiles import merge_profile
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.tracing import outgoing_headers
from app.llm.attempts import count_attempt
from app.llm.settings import LLMSettings

# The smallest context window the app is meant for, for a model it does not know
DEFAULT_CONTEXT_TOKENS = 128_000
# gpt-6-luna holds 1,050,000 tokens, but a request past 272,000 input tokens costs twice
# (OpenAI's model page, read 2026-10-03, decided in the old app)
_CONTEXT_TOKENS: dict[str, int] = {"gpt-6-luna": 272_000}
# Measured with real calls on 2026-09-25 (old app, plan 2026-09-24): efforts none to max but
# not minimal, reasoning context and encrypted reasoning, the cache only behind a breakpoint
_MEASURED_PROFILES: dict[str, dict[str, bool]] = {
    "gpt-6-luna": {
        "supports_thinking": True,
        "thinking_always_enabled": False,
        "openai_supports_reasoning": True,
        "openai_reasoning_enabled_by_default": True,
        "openai_supports_reasoning_effort_none": True,
        "openai_supports_minimal_reasoning_effort": False,
        "openai_responses_supports_reasoning_mode": True,
        "openai_responses_supports_reasoning_context": True,
        "openai_supports_encrypted_reasoning_content": True,
        "openai_supports_prompt_cache_breakpoints": True,
    },
}


class LLMNotConfigured(Exception):
    """No key for the language model is set."""


def build_model(
    settings: LLMSettings, *, transport: httpx2.AsyncBaseTransport | None = None
) -> OpenAIResponsesModel | OpenAIChatModel:
    """The configured model; ``transport`` stands in for the network in a test.

    Build one per process and keep it: it holds an HTTP client with its connection pool, which
    ``await model.client.close()`` releases when the process ends.
    """
    if settings.openai_api_key is None:
        raise LLMNotConfigured("OPENAI_API_KEY is not set: the language model cannot be asked")
    http_client = httpx2.AsyncClient(
        # ten minutes for an answer, five seconds to connect, as pydantic-ai's own client has
        timeout=httpx2.Timeout(600, connect=5),
        event_hooks={"request": [count_attempt, _carry_trace]},
        transport=transport,
    )
    # The SDK asks again after a timeout, a 429 or a 5xx, twice by default, and every request may
    # be paid for: the app waits and asks itself, each time with a reservation (app/llm/calls.py)
    sdk = AsyncOpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key.get_secret_value(),
        http_client=cast(Any, http_client),
        max_retries=0,
    )
    provider = OpenAIProvider(openai_client=sdk)
    profile = _measured_profile(settings.openai_model)
    # max_output_tokens (Responses) or max_completion_tokens (Chat): what an answer may cost at
    # most, reasoning included - the reservation counts on it
    cap = settings.llm_max_output_tokens
    if settings.llm_provider == "openai":
        responses = OpenAIResponsesModelSettings(
            max_tokens=cap,
            openai_reasoning_effort=settings.openai_reasoning_effort,
            openai_text_verbosity=settings.openai_text_verbosity,
        )
        return OpenAIResponsesModel(
            settings.openai_model, provider=provider, settings=responses, profile=profile
        )
    chat = OpenAIChatModelSettings(max_tokens=cap, openai_reasoning_effort=settings.openai_reasoning_effort)
    return OpenAIChatModel(settings.openai_model, provider=provider, settings=chat, profile=profile)


async def _carry_trace(request: httpx2.Request) -> None:
    """The client's request hook: the trace of the request or job the call is made for."""
    request.headers.update(outgoing_headers())


def check_reasoning_effort(settings: LLMSettings) -> None:
    """ValueError where the model's profile says it does not take the configured effort.

    pydantic-ai sends whatever effort it is given, and gpt-6-luna answers ``minimal`` with a
    400 in the middle of a paid job (old app, audit E-84). The profile is the one the model
    gets - the library's, with what was measured laid over it - and only what it says against
    an effort refuses it: a model the library does not describe, a gateway's, is not refused
    what nobody knows. No key is needed, so the start checks it before the key is set.
    """
    profile = _profile(settings.openai_model)
    effort = settings.openai_reasoning_effort
    refused = (effort == "minimal" and profile.get("openai_supports_minimal_reasoning_effort") is False) or (
        effort == "none"
        and profile.get("openai_supports_reasoning") is True
        and profile.get("openai_supports_reasoning_effort_none") is False
    )
    if refused:
        raise ValueError(f"OPENAI_REASONING_EFFORT={effort}: {settings.openai_model} does not take it")


def context_tokens(settings: LLMSettings) -> int:
    """LLM_CONTEXT_TOKENS where set; else the model's where known; else the default."""
    if settings.llm_context_tokens is not None:
        return settings.llm_context_tokens
    known = _known(_CONTEXT_TOKENS, settings.openai_model)
    return DEFAULT_CONTEXT_TOKENS if known is None else known


def _known[T](table: dict[str, T], model_name: str) -> T | None:
    """The entry for the model or a dated snapshot of it (``-YYYY-MM-DD``), never a variant."""
    return next(
        (
            entry
            for name, entry in table.items()
            if re.fullmatch(rf"{re.escape(name)}(-\d{{4}}-\d{{2}}-\d{{2}})?", model_name)
        ),
        None,
    )


def _profile(model_name: str) -> OpenAIModelProfile:
    """As pydantic-ai resolves it for the model, for the keys the library and we set."""
    library = OpenAIProvider.model_profile(model_name)
    return cast(OpenAIModelProfile, merge_profile(library, _measured_profile(model_name)))


def _measured_profile(model_name: str) -> OpenAIModelProfile | None:
    flags = _known(_MEASURED_PROFILES, model_name)
    return None if flags is None else cast(OpenAIModelProfile, flags)
