"""Process settings, read once at start from the environment.

A secret may instead come from a file named by ``<NAME>_FILE`` (Docker and Kubernetes
secrets); the file wins over the plain variable. Errors never echo a value.
"""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, Self, get_args, get_origin

import psycopg
from psycopg.conninfo import conninfo_to_dict
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# The repository's copy; the image sets ONTOLOGY_DIR to the folder it ships
REPOSITORY_ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
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
    """``SecretStr`` itself, constrained (``Annotated``) or optional (``... | None``)."""
    if annotation is SecretStr:
        return True
    if get_origin(annotation) is Annotated:
        return _is_secret(get_args(annotation)[0])
    return any(_is_secret(argument) for argument in get_args(annotation))


def _split_by_the_password(parts: dict[str, Any]) -> bool:
    """Whether an unencoded @, / or : in the password split the URL into wrong parts.

    The signs: an @ inside the host (a leading one names an abstract socket); an @ in the
    database name of a URL that kept no user or password (one with them is a name libpq read
    as written); a port that is no number (padding is fine, libpq strips it).
    """
    host = str(parts.get("host", ""))
    database = str(parts.get("dbname", ""))
    ports = str(parts.get("port", "")).split(",")
    return (
        "@" in host[1:]
        or ("@" in database and not (parts.get("user") or parts.get("password")))
        or not all(re.fullmatch(r"[0-9]*", port.strip()) for port in ports)
    )


def _environment_value(name: str, environment: Mapping[str, str] = os.environ) -> str | None:
    """``name`` in the environment in any case, as pydantic matches the plain variables."""
    if name in environment:
        return environment[name]
    return next((value for key, value in environment.items() if key.upper() == name), None)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(hide_input_in_errors=True)

    database_url: Annotated[SecretStr, Field(min_length=1)]
    # Connections per process: the API holds a few; the cluster's total is replicas times max
    db_pool_min_size: Annotated[int, Field(ge=0)] = 1
    db_pool_max_size: Annotated[int, Field(ge=1)] = 10
    # Loopback unless set: the image sets 0.0.0.0, a developer's start stays off the network
    host: str = "127.0.0.1"
    public_port: Port = 8000
    internal_port: Port = 9000
    # The prefix an ingress serves the API under and strips before it forwards (uvicorn's root
    # path): plain segments without a trailing slash; empty for none
    root_path: Annotated[str, Field(pattern=r"^(/[A-Za-z0-9._~-]+)*$")] = ""
    log_level: LogLevel = "INFO"
    # The server's secret for API key hashes (HMAC); the API does not start without it
    api_key_pepper: Annotated[SecretStr, Field(min_length=32)] | None = None
    # What visitors without a token may do: nothing, look up published curricula, or also search
    public_access: Literal["off", "lookup", "search"] = "off"
    # Failed sign-ins per client address before it is refused for the window
    auth_failure_limit: Annotated[int, Field(ge=1)] = 10
    auth_failure_window_s: Annotated[float, Field(gt=0)] = 900.0
    # A job's lease; the worker renews it at a third. A worker gone silent loses its job after this
    job_lease_s: Annotated[float, Field(ge=3, le=3600)] = 60.0
    # How often an idle worker looks for work
    job_poll_s: Annotated[float, Field(gt=0, le=60)] = 1.0
    ontology_dir: Path = REPOSITORY_ONTOLOGY
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

    @field_validator("database_url")
    @classmethod
    def _usable_connection_string(cls, value: SecretStr) -> SecretStr:
        """Parsed here, so a malformed one stops the start: libpq's own parse error quotes the
        string, password included, and the pool would log it at every attempt."""
        text = value.get_secret_value()
        if not text.strip():
            raise ValueError("must not be blank")
        try:
            parts = conninfo_to_dict(text)
        except (psycopg.ProgrammingError, ValueError):  # ValueError: a byte the system could not decode
            raise ValueError("is not a valid PostgreSQL connection string") from None
        # An unencoded @, / or : in the password splits the URL anew without an error: its rest
        # would be taken for the host, the port or the database name
        if _split_by_the_password(parts):
            raise ValueError("does not parse as meant; write @, / and : in the password as %40, %2F and %3A")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_case_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _ports_differ(self) -> Self:
        if self.internal_port == self.public_port:
            raise ValueError("internal_port must differ from public_port")
        if self.db_pool_max_size < self.db_pool_min_size:
            raise ValueError("db_pool_max_size must not be smaller than db_pool_min_size")
        return self
