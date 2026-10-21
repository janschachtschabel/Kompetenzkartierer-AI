"""Helpers for the tests: settings from invented values only.

Every settings source reads the process environment - ``Settings.model_validate`` included,
as BaseSettings validates through its own ``__init__``. A test built from the real environment
would carry real keys, and pydantic prints input values in its errors. So the variables a
settings class reads are hidden while it is built; those of the operating system stay.
"""

import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings

from app.core.settings import Settings

# A closed port: an app under test that opens its pool reaches no server, and no real one
FAKE_DATABASE_URL = "postgresql://kka:fake@127.0.0.1:1/kka"


def settings_variables(settings_cls: type[BaseSettings]) -> set[str]:
    """Each field's variable and its ``<NAME>_FILE``, upper case."""
    names = {name.upper() for name in settings_cls.model_fields}
    return names | {f"{name}_FILE" for name in names}


@contextmanager
def without_settings_variables(settings_cls: type[BaseSettings] = Settings) -> Iterator[None]:
    """The environment without any variable ``settings_cls`` reads, in any case; restored after."""
    hidden = settings_variables(settings_cls)
    with mock.patch.dict(os.environ):
        for key in [key for key in os.environ if key.upper() in hidden]:
            del os.environ[key]
        yield


def selector_client(app: FastAPI, **options: Any) -> TestClient:
    """A TestClient on a selector event loop: psycopg's async mode refuses Windows' proactor loop."""
    return TestClient(app, backend_options={"loop_factory": asyncio.SelectorEventLoop}, **options)


def make_settings(**values: object) -> Settings:
    """Invented settings; the pool opens no connection until a test asks for one."""
    defaults = {"database_url": FAKE_DATABASE_URL, "db_pool_min_size": 0}
    with without_settings_variables():
        return Settings(**{**defaults, **values})  # type: ignore[arg-type]
