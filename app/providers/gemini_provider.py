import base64
import json
from typing import Any, TypeVar

import httpx
from google import genai
from google.genai import errors, interactions, types
from pydantic import ValidationError

from app.core.config import Settings
from app.prompts.answer import ANSWER_FORMAT_POLICY
from app.prompts.translate import TRANSLATE_POLICY
from app.providers.errors import (
    ProviderInvalidResponse,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
    ProviderUnsupportedLanguage,
)
from app.schemas.common import StrictModel
from app.schemas.question import QuestionResponse
from app.schemas.transcription import TranscriptionResponse
from app.schemas.translation import TranslationChunk


class TranslationResult(StrictModel):
    chunks: list[TranslationChunk]


ParsedModel = TypeVar("ParsedModel", bound=StrictModel)

# The public v1 language grammar is narrower than Gemini's BCP-47 locale list.
# Only send hints with an explicitly verified mapping; never guess a locale.
_HINT_LOCALES = {
    "en": "en-US",
    "en-US": "en-US",
    "en-GB": "en-GB",
    "es": "es-US",
    "es-US": "es-US",
    "fr": "fr-FR",
    "fr-FR": "fr-FR",
    "de": "de-DE",
    "de-DE": "de-DE",
    "pt": "pt-BR",
    "pt-BR": "pt-BR",
    "pt-PT": "pt-PT",
}


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return ProviderTimedOut()
    if isinstance(exc, errors.APIError):
        code = exc.code
        if code in (408, 504):
            return ProviderTimedOut()
        if code == 429:
            return ProviderRateLimited()
        if code == 403 and exc.status == "RESOURCE_EXHAUSTED":
            return ProviderQuotaExceeded()
        return ProviderUnavailable()
    return ProviderUnavailable()


class GeminiProvider:
    """Short-lived requests through one managed async client; no Files API uploads."""

    def __init__(self, settings: Settings, client: genai.Client | None = None) -> None:
        self.settings = settings
        if client is None:
            key = settings.gemini_api_key
            if key is None:
                raise ValueError("Gemini provider requires a server-side key")
            client = genai.Client(
                api_key=key.get_secret_value(),
                http_options=types.HttpOptions(
                    api_version="v1beta",
                    timeout=int(settings.ai_request_timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        self.client = client

    async def close(self) -> None:
        await self.client.aio.aclose()
        self.client.close()

    async def _parse(
        self, model_type: type[ParsedModel], policy: str, payload: dict[str, Any]
    ) -> ParsedModel:
        try:
            response = await self.client.aio.models.generate_content(
                model=self.settings.gemini_text_model,
                contents=json.dumps(payload, ensure_ascii=False),
                config=types.GenerateContentConfig(
                    system_instruction=policy,
                    response_mime_type="application/json",
                    response_json_schema=model_type.model_json_schema(),
                    max_output_tokens=self.settings.max_response_tokens,
                    candidate_count=1,
                    store=False,
                ),
            )
        except (errors.APIError, httpx.TransportError, TimeoutError) as exc:
            raise _map_error(exc) from None
        except (ValidationError, ValueError, TypeError):
            raise ProviderInvalidResponse() from None
        try:
            candidates = response.candidates or []
            if len(candidates) != 1 or candidates[0].finish_reason != types.FinishReason.STOP:
                raise ProviderInvalidResponse()
            text = response.text
            if not text:
                raise ProviderInvalidResponse()
            return model_type.model_validate_json(text)
        except (AttributeError, ValidationError, ValueError, TypeError):
            raise ProviderInvalidResponse() from None

    async def translate(
        self, chunks: list[TranslationChunk], source_language: str, target_language: str
    ) -> list[TranslationChunk]:
        result = await self._parse(
            TranslationResult,
            TRANSLATE_POLICY,
            {
                "source_language": source_language,
                "target_language": target_language,
                "chunks": [chunk.model_dump() for chunk in chunks],
            },
        )
        if len(result.chunks) != len(chunks) or any(
            original.id != translated.id
            for original, translated in zip(chunks, result.chunks, strict=True)
        ):
            raise ProviderInvalidResponse()
        return result.chunks

    async def answer(self, question: str, language: str, context: str) -> QuestionResponse:
        result = await self._parse(
            QuestionResponse,
            ANSWER_FORMAT_POLICY,
            {"question": question, "language": language, "page_context": context},
        )
        if len(result.answer) > self.settings.max_answer_chars or (
            result.source.value == "page" and not context
        ):
            raise ProviderInvalidResponse()
        return result

    async def transcribe(
        self, audio: bytes, media_type: str, language: str | None
    ) -> TranscriptionResponse:
        if media_type != "audio/wav":
            raise ProviderInvalidResponse()
        hint = _HINT_LOCALES.get(language) if language is not None else None
        if language is not None and hint is None:
            raise ProviderUnsupportedLanguage()
        try:
            # Inline bounded audio avoids persistent remote Files API uploads.
            response = await self.client.aio.interactions.create(
                model=self.settings.gemini_transcription_model,
                input=[
                    {
                        "type": "audio",
                        "data": base64.b64encode(audio).decode("ascii"),
                        "mime_type": "audio/wav",
                    }
                ],
                generation_config={
                    "transcription_config": {
                        "mode": "verbatim",
                        "language_codes": [hint] if hint else [],
                    }
                },
                store=False,
                timeout=self.settings.ai_request_timeout_seconds,
            )
        except (errors.APIError, httpx.TransportError, TimeoutError) as exc:
            raise _map_error(exc) from None
        try:
            if not isinstance(response, interactions.Interaction) or response.status != "completed":
                raise ProviderInvalidResponse()
            # The unary plain-text response does not promise one detected language.
            if not response.output_text:
                raise ProviderInvalidResponse()
            result = TranscriptionResponse(text=response.output_text, language=None)
            if len(result.text) > self.settings.max_transcript_chars:
                raise ProviderInvalidResponse()
            return result
        except (AttributeError, ValidationError, ValueError, TypeError):
            raise ProviderInvalidResponse() from None
