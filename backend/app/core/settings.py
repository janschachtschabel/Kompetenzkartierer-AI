"""Process settings, read once at start from the environment.

A secret may instead come from a file named by ``<NAME>_FILE`` (Docker and Kubernetes
secrets); the file wins over the plain variable. Errors never echo a value.
"""

import os
from pathlib import Path
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Port = Annotated[int, Field(ge=1, le=65535)]


class SecretFileSource(PydanticBaseSettingsSource):
    """Reads each secret field (``SecretStr``, optional or not) from the file its ``<NAME>_FILE`` names.

    The file is UTF-8; a byte order mark and the final line end are not part of the secret.
    """

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        variable = f"{field_name.upper()}_FILE"
        path = _environment_value(variable) if _is_secret(field.annotation) else None
        if not path:
            return None, field_name, False
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
        except OSError as error:
            raise ValueError(f"{variable} names a file that cannot be read: {error.strerror}") from None
        except UnicodeDecodeError:  # its message quotes a byte of the secret
            raise ValueError(f"{variable} names a file that is not UTF-8 text") from None
        return content.rstrip("\r\n"), field_name, False

    def __call__(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, field in self.settings_cls.model_fields.items():
            value, key, _ = self.get_field_value(field, name)
            if value is not None:
                values[key] = value
        return values


def _is_secret(annotation: object) -> bool:
    return annotation is SecretStr or SecretStr in get_args(annotation)


def _environment_value(name: str) -> str | None:
    """``name`` in the environment in any case, as pydantic matches the plain variables."""
    if name in os.environ:
        return os.environ[name]
    return next((value for key, value in os.environ.items() if key.upper() == name), None)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    database_url: Annotated[SecretStr, Field(min_length=1)]
    # Loopback unless set: the image sets 0.0.0.0, a developer's start stays off the network
    host: str = "127.0.0.1"
    public_port: Port = 8000
    internal_port: Port = 9000
    # The prefix an ingress serves the API under and strips before it forwards (uvicorn's root
    # path): plain segments without a trailing slash; empty for none
    root_path: Annotated[str, Field(pattern=r"^(/[A-Za-z0-9._~-]+)*$")] = ""
    log_level: LogLevel = "INFO"
    log_format: Literal["text", "json"] = "text"

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

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_case_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _ports_differ(self) -> Self:
        if self.internal_port == self.public_port:
            raise ValueError("internal_port must differ from public_port")
        return self
