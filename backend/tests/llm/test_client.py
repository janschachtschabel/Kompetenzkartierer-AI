"""The model the app talks to: the configured endpoint, the measured profile, no key in sight."""

import io
import json
import logging
from typing import Any

import httpx2
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError

from app.core.logging import configure_logging
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


async def test_the_key_shows_in_no_error_and_no_log_line(restore_logging: None) -> None:
    log = io.StringIO()
    configure_logging("DEBUG", "json", stream=log)
    logging.getLogger("httpx2").setLevel(logging.DEBUG)

    _, error = await ask(llm_settings())

    assert INVENTED_KEY not in str(error)
    assert INVENTED_KEY not in repr(error)
    assert INVENTED_KEY not in log.getvalue()


@pytest.mark.parametrize("name", ["gpt-6-luna", "gpt-6-luna-2026-09-01"])
def test_gpt_6_luna_is_described_as_measured(name: str) -> None:
    profile = build_model(llm_settings(openai_model=name)).profile

    assert profile.get("openai_supports_prompt_cache_breakpoints") is True
    assert profile.get("openai_supports_encrypted_reasoning_content") is True
    assert profile.get("openai_supports_minimal_reasoning_effort") is False


def test_another_model_keeps_the_library_s_profile() -> None:
    profile = build_model(llm_settings(openai_model="gpt-6-luna-mini")).profile

    assert profile.get("openai_supports_prompt_cache_breakpoints") is not True


def test_an_effort_the_model_does_not_take_stops_the_start() -> None:
    with pytest.raises(ValueError, match="OPENAI_REASONING_EFFORT=minimal"):
        check_reasoning_effort(llm_settings(openai_reasoning_effort="minimal"))
    check_reasoning_effort(llm_settings(openai_reasoning_effort="none"))
    check_reasoning_effort(llm_settings(openai_model="some-gateway-model", openai_reasoning_effort="minimal"))


def test_the_context_window_is_the_setting_else_the_model_s_else_the_default() -> None:
    assert context_tokens(llm_settings(llm_context_tokens=64_000)) == 64_000
    assert context_tokens(llm_settings()) == 272_000
    assert context_tokens(llm_settings(openai_model="some-gateway-model")) == DEFAULT_CONTEXT_TOKENS


def test_no_model_without_a_key() -> None:
    with pytest.raises(LLMNotConfigured, match="OPENAI_API_KEY"):
        build_model(llm_settings(openai_api_key=None))
