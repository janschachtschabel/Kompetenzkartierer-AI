"""Fixtures shared by the backend tests."""

import asyncio
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from tests.support import kept_logging


@pytest.fixture(autouse=True)
def without_aws_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """boto3 reads AWS_* and ~/.aws besides the settings: a developer's profile, endpoint or keys
    would steer a test, or sign its requests. Nor does it ask the cloud's metadata address."""
    for key in [key for key in os.environ if key.upper().startswith("AWS_")]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("AWS_CONFIG_FILE", os.devnull)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", os.devnull)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Undo what configure_logging does to the process-wide loggers."""
    with kept_logging():
        yield


# A fresh PostgreSQL database per test, in the server KKA_TEST_DATABASE_URL names: an account
# that may create databases, on a server for tests only (locally the container kka-test-pg, in
# CI a service). Without it the database tests are skipped - unless KKA_REQUIRE_PG or CI is set:
# a CI job that lost the variable would otherwise pass with no database test run.
ADMIN_URL_VARIABLE = "KKA_TEST_DATABASE_URL"


@pytest.fixture
def database_url() -> Iterator[str]:
    admin = os.environ.get(ADMIN_URL_VARIABLE)
    if not admin:
        if os.environ.get("KKA_REQUIRE_PG") or os.environ.get("CI"):
            pytest.fail(f"{ADMIN_URL_VARIABLE} is not set, but the database tests are required")
        pytest.skip(f"{ADMIN_URL_VARIABLE} is not set")
    name = f"kka_t_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
    try:
        yield make_conninfo(admin, dbname=name)
    finally:
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def anyio_backend() -> tuple[str, dict[str, object]]:
    """Async tests run on asyncio's selector loop: psycopg's async mode refuses Windows' proactor."""
    return "asyncio", {"loop_factory": asyncio.SelectorEventLoop}
