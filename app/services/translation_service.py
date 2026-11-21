from pydantic import ValidationError

from app.api.errors import APIError, invalid_upstream
from app.core.config import Settings
from app.providers.base import AIProvider
from app.schemas.common import require_supported_language
from app.schemas.translation import TranslationChunk, TranslationRequest, TranslationResponse


class TranslationService:
    def __init__(self, settings: Settings, provider: AIProvider | None) -> None:
        self.settings = settings
        self.provider = provider

    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        require_supported_language(request.source_language, self.settings.supported_languages)
        require_supported_language(request.target_language, self.settings.supported_languages)
        if (
            len(request.chunks) > self.settings.max_chunks
            or any(len(chunk.text) > self.settings.max_chunk_length for chunk in request.chunks)
            or sum(len(chunk.text) for chunk in request.chunks)
            > self.settings.max_translation_chars
        ):
            raise APIError(413, "PAYLOAD_TOO_LARGE", "Translation exceeds configured limits.")
        if request.source_language == request.target_language:
            chunks = request.chunks
        else:
            if self.provider is None:
                raise APIError(503, "PROVIDER_UNAVAILABLE", "Inference provider is not configured.")
            chunks = await self.provider.translate(
                request.chunks, request.source_language, request.target_language
            )
        try:
            checked = [TranslationChunk.model_validate(chunk) for chunk in chunks]
            if len(checked) != len(request.chunks) or any(
                original.id != translated.id
                for original, translated in zip(request.chunks, checked, strict=True)
            ):
                raise ValueError("Nonmatching translation chunks")
            if (
                any(len(chunk.text) > self.settings.max_chunk_length for chunk in checked)
                or sum(len(chunk.text) for chunk in checked) > self.settings.max_translation_chars
            ):
                raise ValueError("Translation exceeds output limits")
        except (ValidationError, ValueError, TypeError) as exc:
            raise invalid_upstream(exc) from None
        return TranslationResponse(
            source_language=request.source_language,
            target_language=request.target_language,
            chunks=checked,
        )
