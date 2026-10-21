"""Every error the API answers has one JSON shape: ``code``, ``message``, ``details`` (plan §6.4).

``code`` is stable and meant for programs - the frontend picks its own text by it; ``message``
is English for people reading the raw answer. A validation error names the field and the kind
of fault, never the input: a request may carry a password or a key.
"""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

VALIDATION_FAILED = "validation_failed"


def error_response(
    status: int,
    message: str | None = None,
    *,
    code: str | None = None,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """The answer for an error; code and message default to the status's name and phrase."""
    known = HTTPStatus(status)
    body = {
        "code": code or known.name.lower(),
        "message": message or known.phrase,
        "details": dict(details or {}),
    }
    return JSONResponse(body, status_code=status, headers=headers)


async def _http_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, HTTPException)  # noqa: S101 - registered for this type only
    message = error.detail if isinstance(error.detail, str) else None
    return error_response(error.status_code, message, headers=error.headers)


async def _validation_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, RequestValidationError)  # noqa: S101 - registered for this type only
    errors = [{"loc": list(fault["loc"]), "type": fault["type"]} for fault in error.errors()]
    return error_response(
        422, "The request is not valid.", code=VALIDATION_FAILED, details={"errors": errors}
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
