"""The model the app talks to: the configured endpoint, the measured profile, no key in sight."""

import json
import logging
from typing import Any

import httpx2
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.profiles.openai import openai_model_profile
from pydantic_ai.providers.openai import OpenAIProvider

from app.core.tracing import CLIENT_TRACE, continue_trace, end_trace
from app.llm.client import (
    DEFAULT_CONTEXT_TOKENS,
    LLMNotConfigured,
    build_model,
    check_reasoning_effort,
    context_tokens,
)
from app.llm.settings import LLMSettings
from tests.support import without_settings_variables

pytestmark = pytest.mark.anyio

INVENTED_KEY = "sk-invented-0123456789abcdefghijklmnop"


def llm_settings(**values: Any) -> LLMSettings:
    with without_settings_variables(LLMSettings):
        return LLMSettings(**{"openai_api_key": INVENTED_KEY, **values})


class Recorder:
    """A transport in place of the network: keeps each request, answers 401."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(
            401, json={"error": {"message": "Incorrect API key provided", "type": "invalid_request_error"}}
        )


async def ask(settings: LLMSettings) -> tuple[Recorder, BaseException]:
    recorder = Recorder()
    model = build_model(settings, transport=httpx2.MockTransport(recorder))
    with pytest.raises(ModelHTTPError) as caught:
        await Agent(model).run("Nenne ein Thema.")
    return recorder, caught.value


@pytest.mark.parametrize(
    ("provider", "path"),
    [("openai", "/v9/responses"), ("openai-compatible", "/v9/chat/completions")],
)
async def test_the_configured_base_url_and_api_are_used(provider: str, path: str) -> None:
    settings = llm_settings(llm_provider=provider, openai_base_url="https://gateway.example.invalid/v9")

    recorder, _ = await ask(settings)

    [request] = recorder.requests
    assert (request.url.host, request.url.path) == ("gateway.example.invalid", path)
    assert request.headers["authorization"] == f"Bearer {INVENTED_KEY}"


async def test_the_responses_api_carries_effort_and_verbosity() -> None:
    settings = llm_settings(openai_reasoning_effort="high", openai_text_verbosity="medium")

    recorder, _ = await ask(settings)

    body = json.loads(recorder.requests[0].content)
    assert body["reasoning"]["effort"] == "high"
    assert body["text"]["verbosity"] == "medium"
    assert body["model"] == "gpt-6-luna"


async def test_a_chat_gateway_gets_the_effort(restore_logging: None) -> None:
    recorder, _ = await ask(llm_settings(llm_provider="openai-compatible", openai_reasoning_effort="medium"))

    assert json.loads(recorder.requests[0].content)["reasoning_effort"] == "medium"


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_the_sdk_asks_once_and_leaves_the_waiting_to_the_app(status: int) -> None:
    # the SDK would ask twice more on its own, and every request may be paid for
    requests: list[httpx2.Request] = []

    def busy(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(status, json={"error": {"message": "busy", "type": "server_error"}})

    model = build_model(llm_settings(), transport=httpx2.MockTransport(busy))
    with pytest.raises(ModelHTTPError):
        await Agent(model).run("Nenne ein Thema.")

    assert len(requests) == 1


@pytest.mark.parametrize(
    ("provider", "field"),
    [("openai", "max_output_tokens"), ("openai-compatible", "max_completion_tokens")],
)
async def test_each_request_caps_its_answer_reasoning_and_all(provider: str, field: str) -> None:
    default, _ = await ask(llm_settings(llm_provider=provider))
    set_, _ = await ask(llm_settings(llm_provider=provider, llm_max_output_tokens=2_000))

    assert json.loads(default.requests[0].content)[field] == 16_000
    assert json.loads(set_.requests[0].content)[field] == 2_000


async def test_a_request_carries_the_trace_of_the_job_that_sent_it() -> None:
    token = continue_trace("job-trace-0123")
    try:
        recorder, _ = await ask(llm_settings())
    finally:
        end_trace(token)
    untraced, _ = await ask(llm_settings())

    assert recorder.requests[0].headers[CLIENT_TRACE] == "job-trace-0123"
    assert CLIENT_TRACE not in untraced.requests[0].headers


async def test_the_key_shows_in_no_error_and_no_log_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for name in ("openai", "httpx2", "pydantic_ai"):
        caplog.set_level(logging.DEBUG, logger=name)

    _, error = await ask(llm_settings())

    assert INVENTED_KEY not in str(error)
    assert INVENTED_KEY not in repr(error)
    assert caplog.records, "nothing was logged: the check would prove nothing"
    assert INVENTED_KEY not in caplog.text
    assert all(INVENTED_KEY not in repr(record.args) for record in caplog.records)


# Laid over the library's profile, so a misspelt flag would go unnoticed: every one is read back
MEASURED_FLAGS = {
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
}


@pytest.mark.parametrize("provider", ["openai", "openai-compatible"])
@pytest.mark.parametrize("name", ["gpt-6-luna", "gpt-6-luna-2026-09-01"])
def test_gpt_6_luna_is_described_as_measured(provider: str, name: str) -> None:
    profile = build_model(llm_settings(llm_provider=provider, openai_model=name)).profile

    assert {flag: profile.get(flag) for flag in MEASURED_FLAGS} == MEASURED_FLAGS


@pytest.mark.parametrize("name", ["gpt-5.4-mini", "gpt-6-luna-mini", "gpt-6-luna-pro"])
def test_a_model_outside_the_measured_ones_keeps_the_library_s_own_profile(name: str) -> None:
    # not a variant of the measured model either: the library lists variants apart, they differ
    built = build_model(llm_settings(openai_model=name))
    plain = OpenAIResponsesModel(name, provider=OpenAIProvider(api_key=INVENTED_KEY))

    assert built.profile == plain.profile


def test_the_library_does_not_know_gpt_6_luna_yet() -> None:
    # the day it does, the measured entry has done its job: drop it, let the library speak
    assert not openai_model_profile("gpt-6-luna").get("openai_supports_prompt_cache_breakpoints")


@pytest.mark.parametrize(
    ("provider", "model", "effort"),
    [
        ("openai", "gpt-6-luna", "minimal"),
        ("openai-compatible", "gpt-6-luna", "minimal"),
        ("openai", "gpt-5", "none"),
        ("openai-compatible", "gpt-5", "none"),
    ],
)
def test_an_effort_the_model_s_profile_rules_out_stops_the_start(
    provider: str, model: str, effort: str
) -> None:
    # gpt-6-luna reasons from none to max, not at minimal (measured); gpt-5 at every effort but
    # none (the library's profile) - on a gateway's route as on OpenAI's
    settings = llm_settings(llm_provider=provider, openai_model=model, openai_reasoning_effort=effort)

    with pytest.raises(ValueError, match=f"OPENAI_REASONING_EFFORT={effort}"):
        check_reasoning_effort(settings)


@pytest.mark.parametrize(
    ("model", "effort"),
    [
        ("gpt-6-luna", "none"),
        ("gpt-6-luna", "max"),
        ("some-gateway-model", "minimal"),
        ("some-gateway-model", "none"),
    ],
)
def test_an_effort_the_profile_allows_or_does_not_speak_to_is_taken(model: str, effort: str) -> None:
    check_reasoning_effort(llm_settings(openai_model=model, openai_reasoning_effort=effort))


def test_the_effort_is_checked_without_a_key() -> None:
    # the start refuses a wrong effort even before the key is set
    with pytest.raises(ValueError, match="OPENAI_REASONING_EFFORT"):
        check_reasoning_effort(llm_settings(openai_api_key=None, openai_reasoning_effort="minimal"))


def test_the_context_window_is_the_setting_else_the_model_s_else_the_default() -> None:
    assert context_tokens(llm_settings(llm_context_tokens=64_000)) == 64_000
    assert context_tokens(llm_settings()) == 272_000
    assert context_tokens(llm_settings(openai_model="some-gateway-model")) == DEFAULT_CONTEXT_TOKENS


def test_no_model_without_a_key() -> None:
    with pytest.raises(LLMNotConfigured, match="OPENAI_API_KEY"):
        build_model(llm_settings(openai_api_key=None))
