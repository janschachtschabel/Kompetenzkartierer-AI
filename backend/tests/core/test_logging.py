"""Log lines: JSON or text, with request and trace id, one line per event, nothing loud from HTTP clients."""

import contextvars
import io
import json
import logging
import re
import warnings
from collections.abc import Callable
from typing import Any

import pytest

from app.core.logging import (
    MAX_REQUEST_ID_CHARS,
    NO_REQUEST,
    QUIET_LOGGERS,
    configure_logging,
    current_request_id,
    set_request_id,
)
from app.core.tracing import take_trace_headers

ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


pytestmark = pytest.mark.usefixtures("restore_logging")


def configured(format_: str, level: str = "INFO") -> io.StringIO:
    stream = io.StringIO()
    configure_logging(level, format_, stream=stream)
    return stream


def json_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def in_request[T](call: Callable[[], T]) -> T:
    return contextvars.copy_context().run(call)


def test_a_json_line_has_the_agreed_fields() -> None:
    stream = configured("json")

    logging.getLogger("kka.test").info("hello %s", "world")

    [line] = json_lines(stream)
    assert ISO_UTC.match(line["time"])
    assert line["level"] == "INFO"
    assert line["logger"] == "kka.test"
    assert line["message"] == "hello world"
    assert line["request_id"] == NO_REQUEST
    assert line["trace_id"] == NO_REQUEST


def test_a_json_line_names_the_request_and_its_trace() -> None:
    stream = configured("json")

    def handle() -> None:
        request_id = set_request_id("abc-123")
        take_trace_headers([(b"x-client-trace-id", b"trace-9")], request_id)
        logging.getLogger("kka.test").info("inside")

    in_request(handle)

    [line] = json_lines(stream)
    assert line["request_id"] == "abc-123"
    assert line["trace_id"] == "trace-9"


def test_a_traceback_stays_inside_its_json_line() -> None:
    stream = configured("json")

    try:
        raise ValueError("broken")
    except ValueError:
        logging.getLogger("kka.test").exception("failed")

    [line] = json_lines(stream)
    assert "ValueError: broken" in line["exc"]


def test_event_fields_join_the_line_but_never_replace_its_own() -> None:
    stream = configured("json")

    logging.getLogger("kka.test").info("done", extra={"fields": {"status": 200, "level": "forged"}})

    [line] = json_lines(stream)
    assert line["status"] == 200
    assert line["level"] == "INFO"


def test_a_text_line_has_level_logger_request_id_and_message() -> None:
    stream = configured("text")

    logging.getLogger("kka.test").warning("careful")

    assert re.search(r"\| WARNING +\| kka\.test \| - \| careful$", stream.getvalue().strip())


def test_the_level_holds() -> None:
    stream = configured("json", level="WARNING")

    logging.getLogger("kka.test").info("hidden")
    logging.getLogger("kka.test").warning("shown")

    assert [line["message"] for line in json_lines(stream)] == ["shown"]


@pytest.mark.parametrize("name", QUIET_LOGGERS)
def test_http_clients_stay_quiet_even_at_debug(name: str) -> None:
    # httpcore logs response headers at DEBUG; an Authorization header must never reach a line
    configured("json", level="DEBUG")

    assert not logging.getLogger(name).isEnabledFor(logging.DEBUG)
    assert not logging.getLogger(name).isEnabledFor(logging.INFO)


def test_configuring_again_does_not_double_the_lines() -> None:
    configured("json")
    stream = configured("json")

    logging.getLogger("kka.test").info("once")

    assert len(json_lines(stream)) == 1


def test_a_python_warning_becomes_a_log_line() -> None:
    stream = configured("json")

    warnings.warn("old api", DeprecationWarning, stacklevel=1)

    [line] = json_lines(stream)
    assert line["logger"] == "py.warnings"
    assert "old api" in line["message"]


def test_uvicorn_writes_through_the_service_format_without_its_access_line() -> None:
    stream = configured("json", level="WARNING")

    logging.getLogger("uvicorn.error").info("Application startup complete.")
    logging.getLogger("uvicorn.access").info("GET / 200")

    assert [line["message"] for line in json_lines(stream)] == ["Application startup complete."]


def test_a_request_id_keeps_only_harmless_signs_and_is_cut() -> None:
    def run(value: str | None) -> str:
        return in_request(lambda: set_request_id(value))

    assert run("abc\x1b[31m|forged line\n") == "abc31mforgedline"
    assert run("a" * 500) == "a" * MAX_REQUEST_ID_CHARS
    assert re.fullmatch(r"[0-9a-f]{12}", run(None))
    assert re.fullmatch(r"[0-9a-f]{12}", run("\x00\x01"))


def test_the_request_id_holds_for_its_request_only() -> None:
    assert in_request(lambda: (set_request_id("inner"), current_request_id())[1]) == "inner"
    assert current_request_id() == NO_REQUEST
