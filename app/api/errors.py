import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(
        self, status: int, code: str, message: str, headers: dict[str, str] | None = None
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers


def error_response(
    request_id: str, status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={"X-Request-ID": request_id, **(headers or {})},
    )


async def api_error(request: Request, exc: APIError) -> JSONResponse:
    if exc.status >= 500:
        logger.warning("api_failure request_id=%s category=%s", request.state.request_id, exc.code)
    return error_response(request.state.request_id, exc.status, exc.code, exc.message, exc.headers)


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        request.state.request_id, 422, "INVALID_INPUT", "The request could not be processed."
    )


async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else "INVALID_INPUT"
    safe_headers = {
        key: value
        for key, value in (exc.headers or {}).items()
        if key.lower() in {"allow", "retry-after"}
    }
    return error_response(
        request.state.request_id, exc.status_code, code, "Request rejected.", safe_headers
    )


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("api_failure request_id=%s category=unexpected", request.state.request_id)
    return error_response(request.state.request_id, 500, "INTERNAL_ERROR", "Internal server error.")


def invalid_upstream(exc: ValidationError | ValueError) -> APIError:
    return APIError(502, "BAD_UPSTREAM_RESPONSE", "Provider returned an invalid response.")
