import asyncio
import json
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import errors, interactions, types
from pydantic import SecretStr
from test_api import WAV

from app.core.config import Settings
from app.main import create_app
from app.providers.errors import (
    ProviderInvalidResponse,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
    ProviderUnsupportedLanguage,
)
from app.providers.gemini_provider import GeminiProvider
from app.schemas.translation import TranslationChunk


class MockSDK:
    def __init__(self):
        self.text_calls = []
        self.audio_calls = []
        self.text_result: object = {"chunks": [{"id": "a", "text": "Hola"}]}
        self.audio_result: object = interactions.Interaction.model_construct(
            status="completed", output_text="Hola"
        )
        self.async_closed = False
        self.closed = False

        async def generate_content(**kwargs):
            self.text_calls.append(kwargs)
            if isinstance(self.text_result, Exception):
                raise self.text_result
            return SimpleNamespace(
                candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
                text=json.dumps(self.text_result),
            )

        async def create(**kwargs):
            self.audio_calls.append(kwargs)
            if isinstance(self.audio_result, Exception):
                raise self.audio_result
            return self.audio_result

        async def aclose():
            self.async_closed = True

        self.aio = SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content),
            interactions=SimpleNamespace(create=create),
            aclose=aclose,
        )

    def close(self):
        self.closed = True


def provider(sdk: MockSDK) -> GeminiProvider:
    return GeminiProvider(
        Settings(ai_provider="gemini", gemini_api_key=SecretStr("test-only")),
        cast(genai.Client, sdk),
    )


def test_requires_key_and_models_are_configurable():
    with pytest.raises(ValueError, match="server-side key"):
        GeminiProvider(Settings(ai_provider="gemini"))
    with pytest.raises(ValueError, match="Model names"):
        Settings(gemini_text_model="  ")


def test_structured_translation_and_answer_are_validated():
    async def run():
        sdk = MockSDK()
        adapter = provider(sdk)
        chunks = [TranslationChunk(id="a", text="Hello")]
        assert (await adapter.translate(chunks, "en", "es"))[0].text == "Hola"
        call = sdk.text_calls[-1]
        assert call["model"] == "gemini-3.8-flash"
        assert json.loads(call["contents"])["chunks"][0]["text"] == "Hello"
        config = call["config"]
        assert "untrusted" in config.system_instruction
        assert config.response_mime_type == "application/json"
        assert config.max_output_tokens == 600
        assert config.store is False
        assert config.tools is None
        for invalid in (
            {"chunks": [{"id": "b", "text": "Wrong"}]},
            {"chunks": []},
            {"chunks": [{"id": "a", "text": ""}]},
            {"chunks": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}]},
        ):
            sdk.text_result = invalid
            with pytest.raises(ProviderInvalidResponse):
                await adapter.translate(chunks, "en", "es")
        sdk.text_result = {"answer": "Grounded", "source": "page", "context_sufficient": True}
        assert (await adapter.answer("Question?", "es", "Excerpt")).source.value == "page"
        assert json.loads(sdk.text_calls[-1]["contents"])["page_context"] == "Excerpt"
        for invalid in (
            {"answer": "Unsafe", "source": "external", "context_sufficient": False},
            {"answer": "Wrong", "source": "page", "context_sufficient": False},
            {"answer": "x" * 2001, "source": "page", "context_sufficient": True},
        ):
            sdk.text_result = invalid
            with pytest.raises(ProviderInvalidResponse):
                await adapter.answer("Q", "en", "Excerpt")
        original_generate = sdk.aio.models.generate_content

        async def incomplete(**kwargs):
            return SimpleNamespace(
                candidates=[SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)],
                text='{"answer":"partial"}',
            )

        sdk.aio.models.generate_content = incomplete
        with pytest.raises(ProviderInvalidResponse):
            await adapter.answer("Q", "en", "Excerpt")
        sdk.aio.models.generate_content = original_generate
        await adapter.close()
        assert sdk.async_closed and sdk.closed

    asyncio.run(run())


def test_wav_inline_hint_and_transcript_failures():
    async def run():
        sdk = MockSDK()
        adapter = provider(sdk)
        result = await adapter.transcribe(WAV, "audio/wav", "es")
        assert result.text == "Hola" and result.language is None
        call = sdk.audio_calls[-1]
        assert call["model"] == "gemini-3.5-transcribe"
        assert call["store"] is False
        assert call["input"][0]["mime_type"] == "audio/wav"
        assert call["input"][0]["data"].startswith("UklGR")
        assert call["generation_config"]["transcription_config"] == {
            "mode": "verbatim",
            "language_codes": ["es-US"],
        }
        assert (await adapter.transcribe(WAV, "audio/wav", None)).language is None
        assert (
            sdk.audio_calls[-1]["generation_config"]["transcription_config"]["language_codes"] == []
        )
        with pytest.raises(ProviderUnsupportedLanguage):
            await adapter.transcribe(WAV, "audio/wav", "es-MX")
        assert len(sdk.audio_calls) == 2
        for invalid in (
            interactions.Interaction.model_construct(status="failed", output_text="Hola"),
            interactions.Interaction.model_construct(status="completed", output_text=""),
            interactions.Interaction.model_construct(status="completed", output_text="x" * 4001),
            "unexpected response",
        ):
            sdk.audio_result = invalid
            with pytest.raises(ProviderInvalidResponse):
                await adapter.transcribe(WAV, "audio/wav", None)
        with pytest.raises(ProviderInvalidResponse):
            await adapter.transcribe(WAV, "audio/webm", None)

    asyncio.run(run())


@pytest.mark.parametrize(
    ("failure", "mapped"),
    [
        (errors.ClientError(429, {"error": {"message": "private"}}), ProviderRateLimited),
        (
            errors.ClientError(403, {"error": {"status": "RESOURCE_EXHAUSTED"}}),
            ProviderQuotaExceeded,
        ),
        (errors.ClientError(401, {"error": {"message": "private"}}), ProviderUnavailable),
        (errors.ServerError(504, {"error": {"message": "private"}}), ProviderTimedOut),
        (TimeoutError("private"), ProviderTimedOut),
    ],
)
def test_gemini_errors_are_normalized(failure, mapped):
    async def run():
        sdk = MockSDK()
        sdk.text_result = failure
        with pytest.raises(mapped):
            await provider(sdk).translate([TranslationChunk(id="a", text="Hi")], "en", "es")
        sdk.audio_result = failure
        with pytest.raises(mapped):
            await provider(sdk).transcribe(WAV, "audio/wav", None)

    asyncio.run(run())


def test_lifespan_selection_and_three_routes_offline(monkeypatch):
    sdk = MockSDK()

    class FakeGemini(GeminiProvider):
        def __init__(self, settings):
            super().__init__(settings, cast(genai.Client, sdk))

    monkeypatch.setattr("app.providers.factory.GeminiProvider", FakeGemini)
    settings = Settings(ai_provider="gemini", gemini_api_key=SecretStr("test-only"))
    app = create_app(settings)
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert app.state.provider is not None
        assert client.post(
            "/api/v1/translate",
            json={
                "source_language": "en",
                "target_language": "es",
                "chunks": [{"id": "a", "text": "Hello"}],
            },
        ).json()["chunks"] == [{"id": "a", "text": "Hola"}]
        sdk.text_result = {"answer": "Answer", "source": "page", "context_sufficient": True}
        assert (
            client.post(
                "/api/v1/ask",
                json={"question": "What?", "language": "en", "context": {"current_chunk": "Fact"}},
            ).json()["source"]
            == "page"
        )
        response = client.post(
            "/api/v1/transcribe",
            files={"file": ("sample.wav", WAV, "audio/wav")},
            data={"language": "es"},
        )
        assert response.json() == {"text": "Hola", "language": None}
        unsupported = client.post(
            "/api/v1/transcribe",
            files={"file": ("sample.wav", WAV, "audio/wav")},
            data={"language": "es-MX"},
        )
        assert unsupported.status_code == 422
        assert unsupported.json()["error"]["code"] == "UNSUPPORTED_LANGUAGE"
    assert sdk.async_closed and sdk.closed and app.state.provider is None
    without_key = create_app(Settings(ai_provider="gemini"))
    with TestClient(without_key, client=("127.0.0.1", 12345)) as client:
        assert (
            client.post(
                "/api/v1/ask",
                json={"question": "Q", "language": "en", "context": {}},
            ).status_code
            == 503
        )
    with TestClient(
        create_app(Settings(ai_provider="gemini", openai_api_key=SecretStr("other-key"))),
        client=("127.0.0.1", 12345),
    ) as client:
        assert (
            client.post(
                "/api/v1/ask",
                json={"question": "Q", "language": "en", "context": {}},
            ).status_code
            == 503
        )


def test_cancellation_propagates():
    async def run():
        sdk = MockSDK()
        started = asyncio.Event()

        async def pending(**kwargs):
            started.set()
            await asyncio.Event().wait()

        sdk.aio.interactions.create = pending
        task = asyncio.create_task(provider(sdk).transcribe(WAV, "audio/wav", None))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
