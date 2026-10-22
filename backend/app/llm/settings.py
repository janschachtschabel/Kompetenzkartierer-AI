"""The language model's settings: any OpenAI-compatible endpoint, by default OpenAI with gpt-6-luna.

As in the old app (config.py), without the B-API routes: ``openai`` speaks the Responses API,
``openai-compatible`` Chat Completions, both with a Bearer key; OPENAI_BASE_URL points at the
endpoint. A value the endpoint cannot take stops the start rather than a paid job halfway.
The key may come from OPENAI_API_KEY_FILE; without one the app starts, its model calls do not.
"""

import os
import re
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from app.core.settings import EndpointUrl, SecretFileSource, plain_endpoint

# The provider's value sets, compared against the library's types in tests/llm
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
TextVerbosity = Literal["low", "medium", "high"]


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    openai_api_key: Annotated[SecretStr, Field(min_length=1)] | None = None
    openai_base_url: EndpointUrl = "https://api.openai.com/v1"
    openai_model: Annotated[str, Field(min_length=1)] = "gpt-6-luna"
    openai_reasoning_effort: ReasoningEffort = "low"
    openai_text_verbosity: TextVerbosity = "low"
    llm_provider: Literal["openai", "openai-compatible"] = "openai"
    # What one request and its answer may hold together; unset, the model's (app/llm/client.py)
    llm_context_tokens: Annotated[int, Field(ge=8_000)] | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, SecretFileSource(settings_cls), env_settings

    @field_validator("openai_api_key")
    @classmethod
    def _sendable_key(cls, value: SecretStr | None) -> SecretStr | None:
        # The key goes into a header as it is: a space, a line end or a sign outside ASCII makes
        # the HTTP library fail on it and quote the header - the key - in its traceback
        if value is not None and not re.fullmatch(r"[!-~]+", value.get_secret_value()):
            raise ValueError("must be visible ASCII characters only, without spaces or line ends")
        return value

    @field_validator("openai_base_url")
    @classmethod
    def _plain_endpoint(cls, value: str) -> str:
        # http for a gateway inside the cluster
        return plain_endpoint(value)

    @model_validator(mode="after")
    def _no_sdk_request_log(self) -> Self:
        # Set, the openai SDK adds a root log handler of its own on import and logs every
        # request at debug: each line twice, beside the service's own
        if os.environ.get("OPENAI_LOG"):
            raise ValueError(
                "OPENAI_LOG must not be set: the SDK would log requests beside the service's log"
            )
        return self
