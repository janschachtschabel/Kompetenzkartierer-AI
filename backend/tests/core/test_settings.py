"""Settings come from the environment; secrets may come from a file named by <NAME>_FILE.

Only invented values are used here: a settings object built from the real environment
would read real keys, and pydantic would print them in a validation error.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.settings import Settings
from tests.support import FAKE_DATABASE_URL as FAKE_URL
from tests.support import without_settings_variables


@pytest.fixture(autouse=True)
def no_settings_variables() -> Iterator[None]:
    with without_settings_variables():
        yield


def test_defaults_apply_when_only_the_required_value_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)

    settings = Settings()

    assert settings.public_port == 8000
    assert settings.internal_port == 9000
    assert settings.log_level == "INFO"
    assert settings.log_format == "text"
    assert settings.database_url.get_secret_value() == FAKE_URL


def test_a_secret_file_wins_over_the_plain_variable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secret = tmp_path / "database_url"
    secret.write_text("postgresql://kka:from-file@db:5432/kka\n", encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setenv("DATABASE_URL_FILE", str(secret))

    settings = Settings()

    assert settings.database_url.get_secret_value() == "postgresql://kka:from-file@db:5432/kka"


def test_a_missing_secret_file_names_the_variable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL_FILE", str(tmp_path / "absent"))

    with pytest.raises(ValueError, match="DATABASE_URL_FILE"):
        Settings()


def test_a_missing_required_value_names_the_field_and_no_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_PORT", "9123")

    with pytest.raises(ValidationError) as caught:
        Settings()

    assert "database_url" in str(caught.value)
    assert "9123" not in str(caught.value)


def test_an_invalid_value_is_reported_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setenv("PUBLIC_PORT", "not-a-port-SECRET123")

    with pytest.raises(ValidationError) as caught:
        Settings()

    assert "public_port" in str(caught.value)
    assert "SECRET123" not in str(caught.value)


@pytest.mark.parametrize("level", ["LOUD", "", "info "])
def test_an_unknown_log_level_is_refused(monkeypatch: pytest.MonkeyPatch, level: str) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setenv("LOG_LEVEL", level)

    with pytest.raises(ValidationError, match="log_level"):
        Settings()


def test_the_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setenv("LOG_LEVEL", "debug")

    assert Settings().log_level == "DEBUG"


def test_the_server_stays_on_loopback_without_a_root_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)

    settings = Settings()

    assert settings.host == "127.0.0.1"
    assert settings.root_path == ""


def test_a_root_path_is_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setenv("ROOT_PATH", "/kka")

    assert Settings().root_path == "/kka"


@pytest.mark.parametrize("root", ["kka", "/kka/", "/"])
def test_a_root_path_without_a_leading_or_with_a_trailing_slash_is_refused(
    monkeypatch: pytest.MonkeyPatch, root: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setenv("ROOT_PATH", root)

    with pytest.raises(ValidationError, match="root_path"):
        Settings()


def test_the_two_ports_must_differ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", FAKE_URL)
    monkeypatch.setenv("INTERNAL_PORT", "8000")

    with pytest.raises(ValidationError, match="internal_port"):
        Settings()
