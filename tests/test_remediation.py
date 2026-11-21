import asyncio
import io
import logging
import struct
import wave
from typing import cast

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.main import create_app
from app.providers.base import AIProvider
from app.providers.errors import (
    ProviderInvalidResponse,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
)
from app.schemas.question import QuestionContext
from app.services.context_service import ContextService

TRANSLATION = {
    "source_language": "en",
    "target_language": "es",
    "chunks": [{"id": "a", "text": "One"}, {"id": "b", "text": "Two"}],
}
QUESTION = {
    "question": "What is it?",
    "language": "en",
    "context": {"title": "", "current_chunk": "The fact."},
}


def local_client(settings=None, provider=None):
    app = create_app(settings or Settings())
    app.state.provider = provider
    return TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 12345))


def wav_bytes(frames=100):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(1)
        recording.setframerate(8000)
        recording.writeframes(b"\x80" * frames)
    return buffer.getvalue()


def check_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_local_only_and_production_fail_closed():
    with pytest.raises(ValidationError):
        Settings(deployment_mode="production")
    with pytest.raises(ValidationError):
        Settings(deployment_mode="production", trusted_gateway_enabled=True)
    with pytest.raises(ValidationError):
        Settings(
            deployment_mode="production",
            trusted_gateway_enabled=True,
            api_access_key=SecretStr("a" * 32),
        )
    with TestClient(
        create_app(Settings()),
        raise_server_exceptions=False,
        client=("198.51.100.1", 12345),
    ) as remote:
        check_error(remote.post("/api/v1/translate", json=TRANSLATION), 403, "FORBIDDEN")
    with local_client() as client:
        request = TRANSLATION | {"target_language": "en"}
        assert client.post("/api/v1/translate", json=request).status_code == 200


def test_production_auth_direct_requests_and_no_secret_disclosure():
    key = "a-private-gateway-secret-with-32-characters"
    settings = Settings(
        deployment_mode="production",
        trusted_gateway_enabled=True,
        api_access_key=SecretStr(key),
        allowed_origins=["https://app.example"],
    )
    with local_client(settings) as client:
        request = TRANSLATION | {"target_language": "en"}
        for headers in ({}, {"X-Aurora-API-Key": "wrong"}):
            response = client.post("/api/v1/translate", json=request, headers=headers)
            check_error(response, 401, "UNAUTHORIZED")
            assert key not in response.text
        response = client.post("/api/v1/translate", json=request, headers={"X-Aurora-API-Key": key})
        assert response.status_code == 200
        assert key not in response.text
        assert key not in str(settings)
        check_error(client.post("/api/v1/ask", json=QUESTION), 401, "UNAUTHORIZED")
        check_error(
            client.post(
                "/api/v1/transcribe",
                files={"file": ("x.wav", wav_bytes(), "audio/wav")},
            ),
            401,
            "UNAUTHORIZED",
        )


def test_rate_limit_and_recovery(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: clock[0])
    settings = Settings(requests_per_window=1, rate_window_seconds=10)
    with local_client(settings) as client:
        request = TRANSLATION | {"target_language": "en"}
        assert client.post("/api/v1/translate", json=request).status_code == 200
        rejected = client.post("/api/v1/translate", json=request)
        check_error(rejected, 429, "RATE_LIMITED")
        assert rejected.headers["Retry-After"] == "10"
        clock[0] += 11
        assert client.post("/api/v1/translate", json=request).status_code == 200
    limiter = RateLimiter(1, 10)
    assert limiter.check("client-a") is None
    assert limiter.check("client-b") is None
    assert limiter.check("client-a") is not None


def test_context_title_order_dedup_and_limits():
    prepare = ContextService().prepare
    assert prepare(QuestionContext(title="Title")) == "Page title: Title"
    assert prepare(QuestionContext(current_chunk="Current")) == "Current"
    assert (
        prepare(
            QuestionContext(
                title="Title", current_chunk="Current", related_chunks=["current", "Related"]
            )
        )
        == "Page title: Title\nCurrent\nRelated"
    )
    assert prepare(QuestionContext(title="Same", current_chunk="same")) == "Page title: Same"

    class Provider:
        async def answer(self, question, language, context):
            return {"answer": context, "source": "page", "context_sufficient": True}

    with local_client(Settings(max_context_chars=5), Provider()) as client:
        response = client.post("/api/v1/ask", json=QUESTION | {"context": {"title": "Longer"}})
        check_error(response, 413, "PAYLOAD_TOO_LARGE")


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"answer": "Grounded", "source": "page", "context_sufficient": True}, 200),
        ({"answer": "General", "source": "general", "context_sufficient": False}, 200),
        ({"answer": "Unknown", "source": "insufficient", "context_sufficient": False}, 200),
        ({"answer": "Incorrect", "source": "external", "context_sufficient": False}, 502),
        ({"answer": "Incorrect", "source": "page", "context_sufficient": False}, 502),
        ({"answer": "", "source": "general", "context_sufficient": False}, 502),
        ({"answer": "x" * 2001, "source": "page", "context_sufficient": True}, 502),
        ({"source": "page"}, 502),
    ],
)
def test_answer_validation(payload, status):
    class Provider:
        async def answer(self, *args):
            return payload

    with local_client(provider=Provider()) as client:
        response = client.post("/api/v1/ask", json=QUESTION)
        assert response.status_code == status
        if status == 502:
            check_error(response, 502, "BAD_UPSTREAM_RESPONSE")


def test_empty_context_cannot_be_attributed_to_page_and_answer_boundary():
    class Provider:
        async def answer(self, *args):
            return {
                "answer": "x" * 2000,
                "source": "page",
                "context_sufficient": True,
            }

    with local_client(provider=Provider()) as client:
        assert client.post("/api/v1/ask", json=QUESTION).status_code == 200
        response = client.post("/api/v1/ask", json=QUESTION | {"context": {}})
        check_error(response, 502, "BAD_UPSTREAM_RESPONSE")
        response = client.post("/api/v1/ask", json=QUESTION | {"context": {"title": "Only title"}})
        check_error(response, 502, "BAD_UPSTREAM_RESPONSE")
        response = client.post(
            "/api/v1/ask", json=QUESTION | {"context": {"related_chunks": ["  ", "Actual excerpt"]}}
        )
        assert response.status_code == 200


@pytest.mark.parametrize(
    "output",
    [
        [],
        [{"id": "a", "text": "One"}],
        [{"id": "a", "text": "One"}, {"id": "a", "text": "Two"}],
        [{"id": "b", "text": "Two"}, {"id": "a", "text": "One"}],
        [{"id": "a", "text": ""}, {"id": "b", "text": "Two"}],
        {"garbage": True},
    ],
)
def test_translation_provider_invariants(output):
    class Provider:
        async def translate(self, *args):
            return output

    with local_client(provider=Provider()) as client:
        check_error(
            client.post("/api/v1/translate", json=TRANSLATION),
            502,
            "BAD_UPSTREAM_RESPONSE",
        )


def test_translation_combined_limit_and_normalized_configured_languages():
    with local_client(Settings(max_translation_chars=5)) as client:
        check_error(
            client.post(
                "/api/v1/translate",
                json=TRANSLATION | {"target_language": "en"},
            ),
            413,
            "PAYLOAD_TOO_LARGE",
        )
    with local_client(Settings(supported_languages=["en", "es-MX"])) as client:
        request = TRANSLATION | {"source_language": "EN", "target_language": "en"}
        response = client.post("/api/v1/translate", json=request)
        assert response.status_code == 200
        assert response.json()["source_language"] == "en"
        check_error(
            client.post("/api/v1/translate", json=request | {"source_language": "zz"}),
            422,
            "UNSUPPORTED_LANGUAGE",
        )
        check_error(
            client.post("/api/v1/ask", json=QUESTION | {"language": "zz"}),
            422,
            "UNSUPPORTED_LANGUAGE",
        )
        check_error(
            client.post(
                "/api/v1/transcribe",
                files={"file": ("x.wav", wav_bytes(), "audio/wav")},
                data={"language": "zz"},
            ),
            422,
            "UNSUPPORTED_LANGUAGE",
        )
        check_error(
            client.post("/api/v1/translate", json=request | {"source_language": "invalid-tag-4"}),
            422,
            "INVALID_INPUT",
        )


def test_audio_rejection_and_no_provider_invocation():
    calls = []

    class Provider:
        async def transcribe(self, *args):
            calls.append(args)
            return {"text": "OK"}

    valid = wav_bytes()
    variants = []
    variants.append((b"", "audio/wav", 400))
    variants.append((valid[:44], "audio/wav", 400))
    variants.append((valid[:-10], "audio/wav", 400))
    variants.append((b"OggS" + b"\x00" * 23, "audio/ogg", 415))
    variants.append((b"\x1a\x45\xdf\xa3webm", "audio/webm", 415))
    for offset, value in ((24, 0), (22, 0), (32, 0)):
        changed = bytearray(valid)
        struct.pack_into("<I" if offset == 24 else "<H", changed, offset, value)
        variants.append((bytes(changed), "audio/wav", 400 if offset != 22 else 415))
    changed = bytearray(valid)
    struct.pack_into("<H", changed, 20, 3)
    variants.append((bytes(changed), "audio/wav", 415))
    with local_client(provider=Provider()) as client:
        for contents, media_type, status in variants:
            response = client.post(
                "/api/v1/transcribe", files={"file": ("ignored", contents, media_type)}
            )
            assert response.status_code == status, (status, response.text)
        assert calls == []
        assert (
            client.post(
                "/api/v1/transcribe", files={"file": ("ignored", valid, "audio/wav")}
            ).status_code
            == 200
        )
        assert len(calls) == 1


def test_transcript_output_and_result_schema():
    class Provider:
        async def transcribe(self, *args):
            return {"text": "t" * 4001}

    with local_client(provider=Provider()) as client:
        check_error(
            client.post("/api/v1/transcribe", files={"file": ("x.wav", wav_bytes(), "audio/wav")}),
            502,
            "BAD_UPSTREAM_RESPONSE",
        )

    class BoundaryProvider:
        async def transcribe(self, *args):
            return {"text": "t" * 4000}

    with local_client(provider=BoundaryProvider()) as client:
        assert (
            client.post(
                "/api/v1/transcribe", files={"file": ("x.wav", wav_bytes(), "audio/wav")}
            ).status_code
            == 200
        )


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (ProviderUnavailable, 503, "PROVIDER_UNAVAILABLE"),
        (ProviderRateLimited, 429, "PROVIDER_RATE_LIMITED"),
        (ProviderQuotaExceeded, 503, "PROVIDER_QUOTA_EXCEEDED"),
        (ProviderTimedOut, 504, "PROVIDER_TIMEOUT"),
        (ProviderInvalidResponse, 502, "BAD_UPSTREAM_RESPONSE"),
        (RuntimeError, 502, "PROVIDER_FAILURE"),
    ],
)
def test_provider_error_mapping_and_safe_diagnostics(caplog, failure, status, code):
    class Provider:
        async def answer(self, *args):
            raise failure("private page and credential")

    with caplog.at_level(logging.WARNING), local_client(provider=Provider()) as client:
        response = client.post("/api/v1/ask", json=QUESTION)
    check_error(response, status, code)
    assert "private page" not in response.text + caplog.text
    assert response.json()["error"]["request_id"] in caplog.text


def test_http_headers_openapi_and_validation_envelope():
    with local_client() as client:
        wrong_method = client.get("/api/v1/ask")
        check_error(wrong_method, 405, "INVALID_INPUT")
        assert "POST" in wrong_method.headers["Allow"]
        check_error(client.post("/api/v1/ask", json={"question": ""}), 422, "INVALID_INPUT")
        spec = client.get("/openapi.json").json()
        assert set(spec["paths"]) == {
            "/health",
            "/api/v1/translate",
            "/api/v1/ask",
            "/api/v1/transcribe",
        }
        for route in ("/api/v1/translate", "/api/v1/ask", "/api/v1/transcribe"):
            assert "post" in spec["paths"][route]
            assert "ErrorResponse" in str(spec["paths"][route]["post"]["responses"])


def test_provider_cancel_releases_capacity():
    from app.api.dependencies import BoundedProvider

    async def exercise():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class Provider:
            async def answer(self, *args):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        semaphore = asyncio.Semaphore(1)
        bounded = BoundedProvider(cast(AIProvider, Provider()), Settings(), semaphore)
        task = asyncio.create_task(bounded.answer("Q", "en", "context"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert not semaphore.locked()

    asyncio.run(exercise())
