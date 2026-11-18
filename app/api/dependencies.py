import asyncio

from fastapi import Request

from app.api.errors import APIError
from app.core.config import Settings
from app.providers.base import AIProvider
from app.schemas.question import QuestionResponse
from app.schemas.transcription import TranscriptionResponse
from app.schemas.translation import TranslationChunk
from app.services.question_service import QuestionService
from app.services.transcription_service import TranscriptionService
from app.services.translation_service import TranslationService


class BoundedProvider:
    def __init__(self, provider: AIProvider, settings: Settings, semaphore: asyncio.Semaphore):
        self.provider = provider
        self.settings = settings
        self.semaphore = semaphore

    async def _call(self, operation, *args):
        try:
            async with asyncio.timeout(self.settings.ai_request_timeout_seconds):
                async with self.semaphore:
                    return await operation(*args)
        except TimeoutError:
            raise APIError(504, "PROVIDER_TIMEOUT", "Provider request timed out.") from None
        except APIError:
            raise
        except Exception:
            # Provider exceptions can contain private request content. Never include their details.
            raise APIError(503, "PROVIDER_UNAVAILABLE", "Inference provider unavailable.") from None

    async def translate(
        self, chunks: list[TranslationChunk], source_language: str, target_language: str
    ) -> list[TranslationChunk]:
        return await self._call(self.provider.translate, chunks, source_language, target_language)

    async def answer(self, question: str, language: str, context: str) -> QuestionResponse:
        return await self._call(self.provider.answer, question, language, context)

    async def transcribe(
        self, audio: bytes, media_type: str, language: str | None
    ) -> TranscriptionResponse:
        return await self._call(self.provider.transcribe, audio, media_type, language)


def get_provider(request: Request) -> AIProvider | None:
    provider: AIProvider | None = getattr(request.app.state, "provider", None)
    if provider is None:
        return None
    return BoundedProvider(provider, request.app.state.settings, request.app.state.semaphore)


def get_translation_service(request: Request) -> TranslationService:
    return TranslationService(request.app.state.settings, get_provider(request))


def get_question_service(request: Request) -> QuestionService:
    return QuestionService(request.app.state.settings, get_provider(request))


def get_transcription_service(request: Request) -> TranscriptionService:
    return TranscriptionService(request.app.state.settings, get_provider(request))
