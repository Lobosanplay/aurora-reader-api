import asyncio
import hmac
import ipaddress
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.errors import (
    APIError,
    api_error,
    error_response,
    http_error,
    unexpected_error,
    validation_error,
)
from app.api.routes import questions, transcription, translate
from app.core.config import Settings, get_settings
from app.core.rate_limit import RateLimiter
from app.schemas.common import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Aurora Reader API", version="0.1.0")
    app.state.settings = settings
    app.state.provider = None
    app.state.semaphore = asyncio.Semaphore(settings.max_concurrent_provider_requests)
    app.state.rate_limiter = RateLimiter(settings.requests_per_window, settings.rate_window_seconds)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def guard_body(request: Request, call_next):
        request.state.request_id = uuid4().hex
        if request.url.path.startswith("/api/v1/") and request.method == "POST":
            peer = request.client.host if request.client else ""
            if settings.deployment_mode == "local":
                try:
                    loopback = ipaddress.ip_address(peer).is_loopback
                except ValueError:
                    loopback = False
                if not loopback:
                    return error_response(
                        request.state.request_id, 403, "FORBIDDEN", "Local access only."
                    )
            else:
                supplied = request.headers.get("X-Aurora-API-Key", "")
                expected = settings.api_access_key.get_secret_value()
                if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
                    return error_response(
                        request.state.request_id, 401, "UNAUTHORIZED", "Access denied."
                    )
            retry_after = app.state.rate_limiter.check(peer)
            if retry_after is not None:
                return error_response(
                    request.state.request_id,
                    429,
                    "RATE_LIMITED",
                    "Too many requests.",
                    headers={"Retry-After": str(retry_after)},
                )
            max_bytes = (
                settings.max_audio_bytes + 65_536
                if request.url.path == "/api/v1/transcribe"
                else settings.max_json_bytes
            )
            if request.headers.get("content-encoding", "identity").lower() != "identity":
                return error_response(
                    request.state.request_id, 415, "UNSUPPORTED_MEDIA_TYPE", "Encoding unsupported."
                )
            if (
                request.headers.get("content-length", "").isdigit()
                and int(request.headers["content-length"]) > max_bytes
            ):
                return error_response(
                    request.state.request_id, 413, "PAYLOAD_TOO_LARGE", "Request is too large."
                )
            body = bytearray()
            async for part in request.stream():
                body.extend(part)
                if len(body) > max_bytes:
                    return error_response(
                        request.state.request_id, 413, "PAYLOAD_TOO_LARGE", "Request is too large."
                    )
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.add_exception_handler(APIError, api_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(Exception, unexpected_error)

    errors = {
        status: {"model": ErrorResponse}
        for status in (400, 401, 403, 413, 415, 422, 429, 500, 502, 503, 504)
    }
    app.include_router(translate.router, prefix="/api/v1", responses=errors)
    app.include_router(questions.router, prefix="/api/v1", responses=errors)
    app.include_router(transcription.router, prefix="/api/v1", responses=errors)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
