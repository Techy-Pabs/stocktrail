"""The one error format used by every endpoint:

    {"error": {"code": "...", "message": "...", "details": [...]}}

Routes raise ApiError (or one of its subclasses). The handlers below turn
those, FastAPI's own errors (unknown route, wrong method, validation) and
any unexpected exception into that shape.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# The code sent for each status. Anything not listed falls back to "error".
CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}

# Default messages, for errors raised without one (e.g. an unknown route)
MESSAGES = {
    status.HTTP_400_BAD_REQUEST: "The request could not be processed",
    status.HTTP_401_UNAUTHORIZED: "Could not validate credentials",
    status.HTTP_403_FORBIDDEN: "You don't have permission to do this",
    status.HTTP_404_NOT_FOUND: "Not found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Method not allowed",
    status.HTTP_409_CONFLICT: "Conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "The request contains invalid data",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Something went wrong on our side. Please try again later.",
    status.HTTP_503_SERVICE_UNAVAILABLE: "Service unavailable",
}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] = []


class ErrorResponse(BaseModel):
    """The shape of every error response (used in the API docs)."""

    error: ErrorBody


class ApiError(Exception):
    """An error with a status code, sent to the client in the shared format."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.message = message or MESSAGES[self.status_code]
        self.details = details or []
        self.headers = headers
        super().__init__(self.message)


class BadRequest(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST


class NotAuthenticated(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self, message: str | None = None):
        # Tells the client to log in with a Bearer token
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class Forbidden(ApiError):
    status_code = status.HTTP_403_FORBIDDEN


class NotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND


class Conflict(ApiError):
    status_code = status.HTTP_409_CONFLICT


def error_response(
    status_code: int,
    message: str | None = None,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=CODES.get(status_code, "error"),
            message=message or MESSAGES.get(status_code, "Error"),
            details=details or [],
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


def validation_details(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per problem: where it is and what's wrong. Never the value sent.

    Pydantic includes the submitted value under "input", which could be a
    password, so only the location and the message are kept. If a message
    happens to quote the value, it is replaced with a generic one.
    """
    details = []
    for error in errors:
        location, *field = error.get("loc", ())
        message = error.get("msg", "Invalid value")
        value = error.get("input")
        if isinstance(value, str) and value and value in message:
            message = "Invalid value"
        details.append(
            {
                # body, query, path or header
                "location": location,
                # e.g. "email", or "items.0.name" for nested fields; None for the whole body
                "field": ".".join(str(part) for part in field) or None,
                "message": message,
            }
        )
    return details


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    def api_error_handler(request: Request, exc: ApiError):
        return error_response(exc.status_code, exc.message, exc.details, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    def http_error_handler(request: Request, exc: StarletteHTTPException):
        # FastAPI's own errors: unknown route (404), wrong method (405), and any
        # HTTPException. Only our default messages are sent, never exc.detail,
        # so nothing internal leaks. Headers such as Allow are kept.
        return error_response(exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    def validation_error_handler(request: Request, exc: RequestValidationError):
        return error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=validation_details(list(exc.errors())),
        )

    @app.exception_handler(Exception)
    def unexpected_error_handler(request: Request, exc: Exception):
        # The real error goes to the server log only; the client gets a generic 500.
        # exc_info=exc, not logger.exception(): FastAPI runs this handler in a
        # worker thread, where the exception isn't "current", so the traceback
        # would otherwise be lost.
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR)
