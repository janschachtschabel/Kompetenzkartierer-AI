"""Logging: one line per event, as text or JSON, naming the request and the trace it belongs to.

The request id lives in a context variable, so every line written while a request runs names it;
outside a request the field is ``-``. The server logs to stdout, as the platform expects; a
one-shot command that prints a report on stdout logs to stderr. Ported from compendious-text-fastapi.
"""

import json
import logging
import re
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TextIO

from app.core.tracing import trace_id

TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s"
NO_REQUEST = "-"
MAX_REQUEST_ID_CHARS = 64  # a header is caller input; a log line must stay readable
# The signs UUIDs, W3C trace ids and common request ids are written with: a control sign reached
# every line and the answer's header, a space or "|" forged the fields of a text line
_NOT_IN_AN_ID = re.compile("[^A-Za-z0-9._:@+/=-]")
UVICORN_LOGGER = "uvicorn"
UVICORN_ACCESS_LOGGER = "uvicorn.access"  # the service writes its own line per request
# httpx names every request with its query at INFO and httpcore logs headers at DEBUG - an
# Authorization header among them; httpx2 and httpcore2 (starlette's test client) do the same, the
# openai SDK logs request options at DEBUG; botocore logs each signed request at DEBUG (the access
# key id and the signature), urllib3 below it every connection. All stay at WARNING, whatever the level
QUIET_LOGGERS = (
    "httpx",
    "httpcore",
    "httpx2",
    "httpcore2",
    "openai",
    "botocore",
    "boto3",
    "s3transfer",
    "urllib3",
)

_request_id: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST)


def current_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str | None) -> str:
    """Take the caller's id, its harmless signs cut to a log line's measure, or make one.

    The header is cut before the pattern reads it, so a huge header costs nothing.
    """
    cleaned = _NOT_IN_AN_ID.sub("", (value or "")[: 4 * MAX_REQUEST_ID_CHARS])[:MAX_REQUEST_ID_CHARS]
    request_id = cleaned or uuid.uuid4().hex[:12]
    _request_id.set(request_id)
    return request_id


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or _request_id.get()
        return True


class _QuietFilter(logging.Filter):
    """Drops what the HTTP clients log below WARNING, whatever level a library set later.

    The level set in configure_logging alone did not hold: the openai SDK sets its loggers and
    httpx to DEBUG when it is imported with OPENAI_LOG=debug.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        return not any(record.name == name or record.name.startswith(f"{name}.") for name in QUIET_LOGGERS)


class JsonFormatter(logging.Formatter):
    """One JSON object per event; a traceback stays inside its line.

    Fields of an event (``extra={"fields": {...}}``) join the object but never replace its own.
    """

    def format(self, record: logging.LogRecord) -> str:
        moment = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        event: dict[str, object] = {
            "time": moment.replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", NO_REQUEST),
            "trace_id": trace_id() or NO_REQUEST,
            "message": record.getMessage(),
        }
        if record.exc_info:
            event["exc"] = self.formatException(record.exc_info)
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            event.update({key: value for key, value in fields.items() if key not in event})
        return json.dumps(event, ensure_ascii=False, default=str)


class _ServiceHandler(logging.StreamHandler[TextIO]):
    """The root's handler set up here, told apart from handlers others (pytest) put on the root."""


def configure_logging(level: str, format_: str, *, stream: TextIO) -> None:
    """Give the root logger the service's one handler; a repeated call replaces it."""
    root = logging.getLogger()
    for handler in [handler for handler in root.handlers if isinstance(handler, _ServiceHandler)]:
        root.removeHandler(handler)
    handler = _ServiceHandler(stream)
    handler.setFormatter(JsonFormatter() if format_ == "json" else logging.Formatter(TEXT_FORMAT))
    handler.addFilter(_RequestIdFilter())
    root.addHandler(handler)
    # On every root handler, a library's own one too (the openai SDK's basicConfig)
    for each in root.handlers:
        if not any(isinstance(existing, _QuietFilter) for existing in each.filters):
            each.addFilter(_QuietFilter())
    root.setLevel(level)
    # A Python warning wrote its own line to stderr, outside the format a JSON collector reads
    logging.captureWarnings(True)
    # uvicorn's lines go through the root's handler, at INFO whatever the level: it logs its start there
    uvicorn_logger = logging.getLogger(UVICORN_LOGGER)
    uvicorn_logger.handlers.clear()
    uvicorn_logger.propagate = True
    uvicorn_logger.setLevel(logging.INFO)
    access = logging.getLogger(UVICORN_ACCESS_LOGGER)
    access.handlers.clear()
    access.propagate = False
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
