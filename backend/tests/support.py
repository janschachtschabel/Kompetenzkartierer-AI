"""Helpers for the tests: settings from invented values only.

Every settings source reads the process environment - ``Settings.model_validate`` included,
as BaseSettings validates through its own ``__init__``. A test built from the real environment
would carry real keys, and pydantic prints input values in its errors. So the variables a
settings class reads are hidden while it is built; those of the operating system stay.
"""

import asyncio
import atexit
import logging
import os
import shutil
import tempfile
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import cache
from pathlib import Path
from typing import Any
from unittest import mock

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings

from app.core.logging import QUIET_LOGGERS
from app.core.settings import Settings
from app.llm.settings import LLMSettings

TOUCHED_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "py.warnings", *QUIET_LOGGERS)
# A closed port: an app under test that opens its pool reaches no server, and no real one
FAKE_DATABASE_URL = "postgresql://kka:fake@127.0.0.1:1/kka"
FAKE_PEPPER = "invented-pepper-for-tests-0123456789abcdef"


def settings_variables(settings_cls: type[BaseSettings]) -> set[str]:
    """Each field's variable and its ``<NAME>_FILE``, upper case."""
    names = {name.upper() for name in settings_cls.model_fields}
    return names | {f"{name}_FILE" for name in names}


@contextmanager
def without_settings_variables(*settings_classes: type[BaseSettings]) -> Iterator[None]:
    """The environment without any variable the classes read (by default every settings class of
    the app: a process's main builds them all), in any case; restored after."""
    hidden = set().union(*(settings_variables(cls) for cls in settings_classes or (Settings, LLMSettings)))
    with mock.patch.dict(os.environ):
        for key in [key for key in os.environ if key.upper() in hidden]:
            del os.environ[key]
        yield


@contextmanager
def kept_logging() -> Iterator[None]:
    """The process-wide loggers as they were before, whatever configure_logging did meanwhile."""
    loggers = {name: logging.getLogger(name) for name in TOUCHED_LOGGERS}
    saved = {name: (logger.handlers[:], logger.level, logger.propagate) for name, logger in loggers.items()}
    # configure_logging filters every root handler, pytest's own too, which outlive the test
    filters = {handler: handler.filters[:] for handler in logging.getLogger().handlers}
    try:
        yield
    finally:
        logging.captureWarnings(False)
        for name, (handlers, level, propagate) in saved.items():
            logger = logging.getLogger(name)
            logger.handlers[:] = handlers
            logger.setLevel(level)
            logger.propagate = propagate
        for handler, kept in filters.items():
            handler.filters[:] = kept


def selector_client(app: FastAPI, **options: Any) -> TestClient:
    """A TestClient on a selector event loop: psycopg's async mode refuses Windows' proactor loop."""
    return TestClient(app, backend_options={"loop_factory": asyncio.SelectorEventLoop}, **options)


@contextmanager
def lock_held(url: str, statement: str, *, at_most_s: float) -> Iterator[None]:
    """``statement`` (a LOCK) held by another session - for ``at_most_s`` at most.

    A test of a deadline then fails when the deadline regresses, instead of waiting forever.
    """
    taken, done = threading.Event(), threading.Event()

    def hold() -> None:
        with psycopg.connect(url) as connection:
            connection.execute(statement)
            taken.set()
            done.wait(at_most_s)
            connection.rollback()

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    if not taken.wait(10):
        raise TimeoutError(f"could not take: {statement}")
    try:
        yield
    finally:
        done.set()
        holder.join(10)


@cache
def throwaway_store() -> Path:
    """One folder per test process for the apps whose objects no test looks at; removed at exit.
    A test that reads or counts objects passes a store of its own (tmp_path)."""
    folder = Path(tempfile.mkdtemp(prefix="kka-test-store-"))
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    return folder


def make_settings(**values: object) -> Settings:
    """Invented settings; the pool opens no connection until a test asks for one, and the app
    opens a file system store (the API needs one to start)."""
    defaults = {
        "database_url": FAKE_DATABASE_URL,
        "api_key_pepper": FAKE_PEPPER,
        "db_pool_min_size": 0,
        "storage_dir": throwaway_store(),
    }
    with without_settings_variables():
        return Settings(**{**defaults, **values})  # type: ignore[arg-type]


@asynccontextmanager
async def loop_watch(tick_s: float = 0.01) -> AsyncIterator[list[float]]:
    """The longest the running loop went without turning, measured while the block runs.

    A coroutine that wakes every ``tick_s`` notes the gap between its wakes; a call that holds
    the loop (a blocking read, a sleep in a coroutine) shows as a gap that long. The list holds
    one number, the longest gap, once the block has ended.
    """
    longest = [0.0]
    done = asyncio.Event()

    async def tick() -> None:
        last = time.perf_counter()
        while not done.is_set():
            await asyncio.sleep(tick_s)
            now = time.perf_counter()
            longest[0] = max(longest[0], now - last)
            last = now

    watcher = asyncio.create_task(tick())
    try:
        yield longest
    finally:
        done.set()
        await watcher


def seed_token(url: str, name: str, roles: list[str]) -> str:
    """A new account with ``roles`` in a migrated test database, and its token."""
    from app.db.accounts import create_account, issue_key

    async def seed() -> str:
        async with await psycopg.AsyncConnection.connect(url, autocommit=True) as connection:
            account = await create_account(connection, name, roles)
            _, token = await issue_key(connection, account, "seed", FAKE_PEPPER)
        return token

    return asyncio.run(seed(), loop_factory=asyncio.SelectorEventLoop)


def seed_admin(url: str) -> dict[str, str]:
    """The Authorization header of a new admin in a migrated test database."""
    return {"Authorization": f"Bearer {seed_token(url, 'Admin', ['admin'])}"}
