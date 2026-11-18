from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


def error_response(request_id: str, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
        headers={"X-Request-ID": request_id},
    )


async def api_error(request: Request, exc: APIError) -> JSONResponse:
    return error_response(request.state.request_id, exc.status, exc.code, exc.message)


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        request.state.request_id, 422, "INVALID_INPUT", "The request could not be processed."
    )


async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else "INVALID_INPUT"
    return error_response(request.state.request_id, exc.status_code, code, "Request rejected.")


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return error_response(request.state.request_id, 500, "INTERNAL_ERROR", "Internal server error.")


def invalid_upstream(exc: ValidationError | ValueError) -> APIError:
    return APIError(502, "BAD_UPSTREAM_RESPONSE", "Provider returned an invalid response.")
