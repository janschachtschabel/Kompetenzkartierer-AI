"""The language model's settings: OpenAI-compatible, base URL changeable, values the library takes."""

import typing
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

from app.llm.settings import LLMSettings
from tests.support import without_settings_variables

INVENTED_KEY = "sk-invented-0123456789abcdefghijklmnop"


@pytest.fixture(autouse=True)
def no_llm_variables() -> Iterator[None]:
    with without_settings_variables(LLMSettings):
        yield


def literal_values(annotation: object) -> set[str]:
    """The values of a Literal, also inside Optional[...]."""
    if typing.get_origin(annotation) is typing.Literal:
        return set(typing.get_args(annotation))
    return {value for argument in typing.get_args(annotation) for value in literal_values(argument)}


def test_the_defaults_follow_the_old_app() -> None:
    settings = LLMSettings()

    assert (settings.openai_base_url, settings.openai_model) == ("https://api.openai.com/v1", "gpt-6-luna")
    assert (settings.openai_reasoning_effort, settings.openai_text_verbosity) == ("low", "low")
    assert (settings.llm_provider, settings.llm_context_tokens, settings.openai_api_key) == (
        "openai",
        None,
        None,
    )


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("LLM_PROVIDER", "b-api-openai"),
        ("OPENAI_REASONING_EFFORT", "extreme"),
        ("OPENAI_TEXT_VERBOSITY", "chatty"),
        ("OPENAI_BASE_URL", "api.openai.com/v1"),
        ("OPENAI_BASE_URL", "ftp://gateway.example.invalid/v1"),
        ("OPENAI_BASE_URL", "https://user:invented-password@gateway.example.invalid/v1"),
        ("OPENAI_BASE_URL", "https://gateway.example.invalid/v1?key=invented-query"),
        ("OPENAI_BASE_URL", "https://gateway.example.invalid/v1#invented-part"),
        ("OPENAI_BASE_URL", "https://gateway.example.invalid:99999/v1"),
        ("OPENAI_BASE_URL", "https:///v1"),
        ("LLM_CONTEXT_TOKENS", "100"),
    ],
    ids=[
        "provider",
        "effort",
        "verbosity",
        "no-scheme",
        "ftp",
        "userinfo",
        "query",
        "fragment",
        "port",
        "no-host",
        "context",
    ],
)
def test_a_value_the_endpoint_cannot_take_stops_the_start(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError, match=variable.lower()) as caught:
        LLMSettings()

    assert value not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    ["https://gateway.example.invalid", "http://127.0.0.1:8080/v1", "https://gateway.example.invalid/a/v1"],
)
def test_a_plain_endpoint_is_taken_as_written(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    # http too: a gateway inside the cluster may speak it
    monkeypatch.setenv("OPENAI_BASE_URL", url)

    assert LLMSettings().openai_base_url == url


# A sign that is no visible ASCII character makes the HTTP library fail on the header and quote
# it whole in the traceback: a space, a tab, a line end, a no-break space, an umlaut
UNSENDABLE = [" ", chr(0x09), chr(0x0A), chr(0xA0), chr(0xE4)]


@pytest.mark.parametrize("sign", UNSENDABLE, ids=["space", "tab", "newline", "nbsp", "umlaut"])
def test_a_key_that_cannot_be_sent_stops_the_start(monkeypatch: pytest.MonkeyPatch, sign: str) -> None:
    key = INVENTED_KEY[:10] + sign + INVENTED_KEY[10:]
    monkeypatch.setenv("OPENAI_API_KEY", key)

    with pytest.raises(ValidationError, match="openai_api_key") as caught:
        LLMSettings()

    assert INVENTED_KEY[10:] not in str(caught.value)


def test_a_key_file_with_a_trailing_space_stops_the_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # only the final line end is not part of the secret
    secret = tmp_path / "openai_api_key"
    secret.write_text(INVENTED_KEY + " \n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))

    with pytest.raises(ValidationError, match="openai_api_key") as caught:
        LLMSettings()

    assert INVENTED_KEY not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "library_field"),
    [
        ("openai_reasoning_effort", "openai_reasoning_effort"),
        ("openai_text_verbosity", "openai_text_verbosity"),
    ],
)
def test_the_accepted_values_are_the_library_s_own(field: str, library_field: str) -> None:
    ours = literal_values(LLMSettings.model_fields[field].annotation)
    theirs = literal_values(typing.get_type_hints(OpenAIResponsesModelSettings)[library_field])

    assert ours == theirs


def test_the_sdk_s_own_request_log_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # OPENAI_LOG makes the SDK set up a root handler of its own and log requests at debug
    monkeypatch.setenv("OPENAI_LOG", "debug")

    with pytest.raises(ValidationError, match="OPENAI_LOG"):
        LLMSettings()


def test_the_key_comes_from_its_file_and_never_shows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = tmp_path / "openai_api_key"
    secret.write_text(INVENTED_KEY + "\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret))

    settings = LLMSettings()

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == INVENTED_KEY
    assert INVENTED_KEY not in repr(settings) + str(settings)
