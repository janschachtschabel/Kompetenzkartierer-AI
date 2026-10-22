"""Process settings, read once at start from the environment.

A secret may instead come from a file named by ``<NAME>_FILE`` (Docker and Kubernetes
secrets); the file wins over the plain variable. Errors never echo a value.
"""

import ipaddress
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal, Self, get_args, get_origin
from urllib.parse import urlsplit

import psycopg
from psycopg.conninfo import conninfo_to_dict
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# The repository's copy; the image sets ONTOLOGY_DIR to the folder it ships
REPOSITORY_ONTOLOGY = Path(__file__).resolve().parents[3] / "ontology"
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Port = Annotated[int, Field(ge=1, le=65535)]
# A DNS label as botocore takes it: letters, digits and "-", not at either end
_HOST_LABEL = re.compile(r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)")
# The address of a service the process calls: the language model, the object store
EndpointUrl = Annotated[str, Field(pattern=r"^https?://[^\s/]+(/\S*)?$")]


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


def plain_endpoint(value: str) -> str:
    """``value`` if it is http(s)://host[:port][/path]; http for a service inside the cluster.

    A user, a query or a fragment would ride along on every request and into logs.
    """
    parts = urlsplit(value)
    try:
        port_valid = parts.port is None or parts.port > 0
    except ValueError:  # out of range
        port_valid = False
    if not parts.hostname or "@" in parts.netloc or "?" in value or "#" in value or not port_valid:
        raise ValueError("must be http(s)://host[:port][/path], without user, query or fragment")
    return value


def _s3_host(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.rstrip(".").split(".")
        return len(hostname) <= 255 and all(_HOST_LABEL.fullmatch(label) for label in labels)
    return True


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
    # How long a request waits for a pool connection before it answers 503
    db_pool_timeout_s: Annotated[float, Field(gt=0, le=60)] = 5.0
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
    # The proxies (ingress, web server) whose X-Forwarded-For names the client: addresses or
    # networks, never "*" - with it every client could name its own address and dodge the limit
    forwarded_allow_ips: str = "127.0.0.1,::1"
    # Failed sign-ins per source (address, IPv6 /64) before its further failures get 429 for
    # the window; a valid token always passes
    auth_failure_limit: Annotated[int, Field(ge=1)] = 10
    auth_failure_window_s: Annotated[float, Field(gt=0)] = 900.0
    # A job's lease; the worker renews it at a third. A worker gone silent loses its job after this
    job_lease_s: Annotated[float, Field(ge=3, le=3600)] = 60.0
    # How often an idle worker looks for work
    job_poll_s: Annotated[float, Field(gt=0, le=60)] = 1.0
    # How long a stopping worker lets its job run before it hands it back unspent; keep it below
    # the deployment's termination grace period (Kubernetes: 30 s), or the job waits for its lease
    job_shutdown_grace_s: Annotated[float, Field(ge=0, le=3600)] = 20.0
    ontology_dir: Path = REPOSITORY_ONTOLOGY
    log_format: Literal["text", "json"] = "text"
    # Where objects go: a folder (development, one node) or an S3-compatible service (a cluster)
    storage_backend: Literal["fs", "s3"] = "fs"
    # The folder for the file system store; the store does not open without it
    storage_dir: Path | None = None
    # The S3 service: its address (empty for AWS itself), bucket and region; the keys come both or
    # neither - without them boto3 takes the credentials of the pod or machine
    s3_endpoint_url: EndpointUrl | None = None
    s3_bucket: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")] | None = None
    s3_region: Annotated[str, Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")] = "us-east-1"
    s3_access_key: Annotated[SecretStr, Field(min_length=1)] | None = None
    s3_secret_key: Annotated[SecretStr, Field(min_length=1)] | None = None

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

    @field_validator("forwarded_allow_ips")
    @classmethod
    def _proxy_networks(cls, value: str) -> str:
        entries = [entry.strip() for entry in value.split(",")]
        try:
            # strict: 10.42.1.5/16 is no network, and taking it as 10.42.0.0/16 would trust more
            networks = [ipaddress.ip_network(entry, strict=True) for entry in entries]
        except ValueError:
            raise ValueError("must list proxy addresses or networks, comma-separated, never *") from None
        if any(net.prefixlen == 0 for net in networks):
            raise ValueError("must not trust every address (/0): every client could name its own")
        # a single address without its /32 or /128, a network with its prefix
        return ",".join(str(net.network_address) if net.num_addresses == 1 else str(net) for net in networks)

    @field_validator("s3_endpoint_url", mode="before")
    @classmethod
    def _empty_endpoint_is_aws(cls, value: object) -> object:
        # The Helm values write S3_ENDPOINT_URL: "" for AWS itself; boto3 refuses "" as an address
        return None if value == "" else value

    @field_validator("s3_endpoint_url")
    @classmethod
    def _plain_s3_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # boto3 refuses a host name with "_" (a Compose service name may have one) only as it
        # builds the client, quoting the address; here the start stops, naming the setting
        if not _s3_host(urlsplit(plain_endpoint(value)).hostname or ""):
            raise ValueError("must name a host of letters, digits, dots and hyphens, or an IP address")
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
        if self.storage_backend == "s3" and self.s3_bucket is None:
            raise ValueError("s3_bucket is needed for storage_backend=s3")
        if (self.s3_access_key is None) != (self.s3_secret_key is None):
            raise ValueError("s3_access_key and s3_secret_key come both or neither")
        return self
