"""The test helpers build settings from invented values only, whatever the environment holds."""

import pytest

from tests.support import make_settings


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
