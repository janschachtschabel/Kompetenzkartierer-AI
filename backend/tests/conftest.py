"""Fixtures shared by the backend tests."""

import asyncio
import logging
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from app.core.logging import QUIET_LOGGERS

TOUCHED_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "py.warnings", *QUIET_LOGGERS)


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """Undo what configure_logging does to the process-wide loggers."""
    loggers = {name: logging.getLogger(name) for name in TOUCHED_LOGGERS}
    saved = {name: (logger.handlers[:], logger.level, logger.propagate) for name, logger in loggers.items()}
    yield
    logging.captureWarnings(False)
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate


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
