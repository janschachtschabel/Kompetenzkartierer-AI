"""The test helpers build settings from invented values only, whatever the environment holds."""

import io
import logging
import os

import pytest

from app.core.logging import configure_logging
from tests.support import kept_logging, make_settings, without_settings_variables


def test_test_settings_ignore_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # every settings source reads the environment, Settings.model_validate included
    monkeypatch.setenv("PUBLIC_PORT", "1234")
    monkeypatch.setenv("public_port", "1235")
    monkeypatch.setenv("DATABASE_URL_FILE", "/nonexistent/invented")

    settings = make_settings()

    assert settings.public_port == 8000
    assert settings.database_url.get_secret_value().startswith("postgresql://kka:fake@")


def test_test_settings_take_the_values_given() -> None:
    assert make_settings(internal_port=9100).internal_port == 9100


def test_the_hidden_variables_are_those_of_every_settings_class(monkeypatch: pytest.MonkeyPatch) -> None:
    # serve and worker build the language model's settings too: a test of their main must not
    # carry the real key
    monkeypatch.setenv("OPENAI_API_KEY", "sk-invented-to-be-hidden")
    monkeypatch.setenv("openai_api_key_file", "/nonexistent/invented")
    monkeypatch.setenv("DATABASE_URL", "postgresql://invented@127.0.0.1:1/x")

    with without_settings_variables():
        left = {key.upper() for key in os.environ}

    assert {"OPENAI_API_KEY", "OPENAI_API_KEY_FILE", "DATABASE_URL"}.isdisjoint(left)


def test_kept_logging_undoes_what_configure_logging_does() -> None:
    # stands for pytest's own capture handler, which lives across tests: a filter left on it
    # hid the HTTP clients' lines from caplog in every later test
    lasting = logging.NullHandler()
    root = logging.getLogger()
    root.addHandler(lasting)
    try:
        before = (root.level, logging.getLogger("openai").level)
        with kept_logging():
            configure_logging("DEBUG", "json", stream=io.StringIO())

        assert lasting.filters == []
        assert (root.level, logging.getLogger("openai").level) == before
        assert lasting in root.handlers
    finally:
        root.removeHandler(lasting)
