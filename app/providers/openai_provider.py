import io
import json

from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
from pydantic import ValidationError

from app.core.config import Settings
from app.prompts.answer import ANSWER_POLICY
from app.prompts.translate import TRANSLATE_POLICY
from app.providers.errors import (
    ProviderInvalidResponse,
    ProviderQuotaExceeded,
    ProviderRateLimited,
    ProviderTimedOut,
    ProviderUnavailable,
)
from app.schemas.common import StrictModel, validate_language
from app.schemas.question import QuestionResponse
from app.schemas.transcription import TranscriptionResponse
from app.schemas.translation import TranslationChunk


class TranslationResult(StrictModel):
    chunks: list[TranslationChunk]


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, APITimeoutError):
        return ProviderTimedOut()
    if isinstance(exc, APIResponseValidationError):
        return ProviderInvalidResponse()
    if isinstance(exc, RateLimitError):
        body = exc.body
        code = body.get("code") if isinstance(body, dict) else None
        nested = body.get("error") if isinstance(body, dict) else None
        if isinstance(nested, dict):
            code = nested.get("code")
        if exc.code == "insufficient_quota" or code == "insufficient_quota":
            return ProviderQuotaExceeded()
        return ProviderRateLimited()
    if isinstance(exc, (AuthenticationError, APIConnectionError)):
        return ProviderUnavailable()
    if isinstance(exc, BadRequestError):
        return ProviderUnavailable()
    if isinstance(exc, APIStatusError):
        if exc.status_code in (500, 502, 503):
            return ProviderUnavailable()
        if exc.status_code == 504:
            return ProviderTimedOut()
        return ProviderUnavailable()
    return ProviderUnavailable()


class OpenAIProvider:
    """One app-lifetime SDK client; no provider request/response content is logged."""

    def __init__(self, settings: Settings, client: AsyncOpenAI | None = None) -> None:
        self.settings = settings
        self.client = client or AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.ai_request_timeout_seconds,
            max_retries=0,
        )

    async def close(self) -> None:
        await self.client.close()

    async def _parse(
        self,
        model_type: type[TranslationResult] | type[QuestionResponse],
        policy: str,
        payload: dict,
    ):
        try:
            response = await self.client.responses.parse(
                model=self.settings.openai_text_model,
                instructions=policy,
                input=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                text_format=model_type,
                max_output_tokens=self.settings.max_response_tokens,
                reasoning={"effort": "none"},
                store=False,
            )
        except (
            APITimeoutError,
            APIStatusError,
            APIConnectionError,
            APIResponseValidationError,
        ) as exc:
            raise _map_error(exc) from None
        except (ValidationError, ValueError, TypeError):
            raise ProviderInvalidResponse() from None
        try:
            complete = response.status == "completed" and response.output_parsed is not None
        except (AttributeError, ValueError, TypeError):
            raise ProviderInvalidResponse() from None
        if not complete:
            raise ProviderInvalidResponse()
        try:
            return model_type.model_validate(response.output_parsed)
        except (ValidationError, ValueError, TypeError):
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
            ANSWER_POLICY
            + " Return 2–4 concise sentences. A page title alone does not prove a claim. "
            "For general knowledge explicitly signal that it is not from the page. "
            "Use source=page only if the supplied excerpts support the claims; otherwise "
            "use general or insufficient. Set context_sufficient true only for page.",
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
        # The SDK accepts a (filename, bytes, MIME) tuple without writing a temporary file.
        if media_type != "audio/wav":
            raise ProviderInvalidResponse()
        kwargs = {"languages": [language]} if language else {}
        try:
            with io.BytesIO(audio) as buffer:
                response = await self.client.audio.transcriptions.create(
                    model=self.settings.openai_transcription_model,
                    file=("recording.wav", buffer, "audio/wav"),
                    **kwargs,
                )
        except (
            APITimeoutError,
            APIStatusError,
            APIConnectionError,
            APIResponseValidationError,
        ) as exc:
            raise _map_error(exc) from None
        try:
            detected = response.languages or []
            code = validate_language(detected[0].code) if len(detected) == 1 else None
            result = TranscriptionResponse(text=response.text, language=code)
            if len(result.text) > self.settings.max_transcript_chars:
                raise ValueError("Transcript too long")
            return result
        except (AttributeError, ValidationError, ValueError, TypeError):
            raise ProviderInvalidResponse() from None
