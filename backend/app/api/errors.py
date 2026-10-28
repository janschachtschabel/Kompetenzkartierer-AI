"""The errors the application answers have one JSON shape: ``code``, ``message``, ``details`` (§6.4).

``code`` is stable and meant for programs - the frontend picks its own text by it; ``message``
is English for people reading the raw answer. The codes are a fixed table, not the names of
Python's HTTPStatus, which a Python release may rename (3.13 did for 413 and 422). A validation
error names the path to the field and the kind of fault, never a value; a key the model does
not know is masked as ``_``, as the caller chose it. uvicorn answers a request it cannot parse
before the application sees it, in plain text.
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.utils import is_body_allowed_for_status_code
from psycopg import OperationalError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

log = logging.getLogger(__name__)

VALIDATION_FAILED = "validation_failed"
MASKED = "_"
CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    410: "gone",
    412: "precondition_failed",
    413: "content_too_large",
    415: "unsupported_media_type",
    422: "unprocessable_content",
    429: "too_many_requests",
    500: "internal_server_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


class Refusal(HTTPException):
    """A refusal with a code of its own, for one the frontend words apart from others of its
    status (``file_too_large`` beside a body cut at the limit); ``details`` what the page needs
    to go on (the check that runs already)."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: Mapping[str, str] | None = None,
        details: Mapping[str, Any] | None = None,
    ):
        super().__init__(status_code, message, dict(headers) if headers else None)
        self.code = code
        self.details = dict(details or {})


class ErrorBody(BaseModel):
    """The body of every error answer, as the OpenAPI spec documents it."""

    code: str
    message: str
    details: dict[str, Any] = {}


DATABASE_RETRY_S = 5
_REFUSAL = {"model": ErrorBody}
# Documented on the routers whose operations need a token
AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {**_REFUSAL, "description": "No valid token"},
    403: {**_REFUSAL, "description": "The token's account lacks the role"},
    429: {**_REFUSAL, "description": "Too many failed sign-ins from this address"},
}
# Documented for every operation in place of FastAPI's own validation error shape
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorBody, "description": "The request is not valid"},
}


def error_response(
    status: int,
    message: str | None = None,
    *,
    code: str | None = None,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """The answer for an error; code and message default to the status's code and phrase.

    A status that allows no body (204, 304) answers without one, as HTTP requires.
    """
    if not is_body_allowed_for_status_code(status):
        return Response(status_code=status, headers=headers)
    body = ErrorBody(
        code=code or CODES.get(status, f"http_{status}"),
        message=message or _phrase(status),
        details=dict(details or {}),
    )
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


async def _http_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, HTTPException)  # noqa: S101 - registered for this type only
    detail = error.detail
    message = detail if isinstance(detail, str) else None
    details: Mapping[str, Any] | None = detail if isinstance(detail, Mapping) else None
    code = error.code if isinstance(error, Refusal) else None
    if isinstance(error, Refusal) and error.details:
        details = error.details
    return error_response(error.status_code, message, code=code, details=details, headers=error.headers)


async def _validation_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, RequestValidationError)  # noqa: S101 - registered for this type only
    errors = [{"loc": _location(fault), "type": fault["type"]} for fault in error.errors()]
    return error_response(
        422, "The request is not valid.", code=VALIDATION_FAILED, details={"errors": errors}
    )


def _location(fault: Mapping[str, Any]) -> list[Any]:
    location = list(fault["loc"])
    if fault["type"] == "extra_forbidden" and location:
        location[-1] = MASKED
    if len(location) > 1 and location[-1] == "[key]":  # a mapping's key, as the request had it
        location[-2] = MASKED
    return location


# The states of a database that is away: no connection (class 08), shut down or starting
# (57P01-57P03). A deadlock, a cancelled statement, a full disk is a fault, not a reason to retry
_AWAY_STATES = ("57P01", "57P02", "57P03")


def _database_is_away(error: OperationalError) -> bool:
    # PoolTimeout and a connection the client could not make carry no state
    state = error.sqlstate
    return state is None or state.startswith("08") or state in _AWAY_STATES


async def _database_away(request: Request, error: Exception) -> Response:
    """No pool connection in time, or the database cut it: try again soon. Any other operational
    error goes on to the 500 answer and its traceback in the log."""
    assert isinstance(error, OperationalError)  # noqa: S101 - registered for this type only
    if not _database_is_away(error):
        raise error
    # the class and the state: a path is the request log's, and quotes the client. Without a
    # state the error is psycopg's own - a lost connection, or a refusal such as too many
    # parameters - and its words, which quote no data, are what tells them apart
    said = "" if error.sqlstate else " ".join(str(error).split())
    log.warning("the database did not answer: %s %s %s", type(error).__name__, error.sqlstate, said)
    retry = {"Retry-After": str(DATABASE_RETRY_S)}
    return error_response(503, "The database does not answer; try again shortly.", headers=retry)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(OperationalError, _database_away)
