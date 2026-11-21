from pydantic import ValidationError

from app.api.errors import APIError, invalid_upstream
from app.core.config import Settings
from app.providers.base import AIProvider
from app.schemas.common import require_supported_language
from app.schemas.question import QuestionRequest, QuestionResponse
from app.services.context_service import ContextService


class QuestionService:
    def __init__(self, settings: Settings, provider: AIProvider | None) -> None:
        self.settings = settings
        self.provider = provider

    async def answer(self, request: QuestionRequest) -> QuestionResponse:
        require_supported_language(request.language, self.settings.supported_languages)
        context = request.context
        if (
            len(request.question) > self.settings.max_question_length
            or len(context.related_chunks) > self.settings.max_related_chunks
            or sum(map(len, [context.title, context.current_chunk, *context.related_chunks]))
            > self.settings.max_context_chars
        ):
            raise APIError(413, "PAYLOAD_TOO_LARGE", "Question context exceeds configured limits.")
        if self.provider is None:
            raise APIError(503, "PROVIDER_UNAVAILABLE", "Inference provider is not configured.")
        prepared = ContextService().prepare(context)
        try:
            result = await self.provider.answer(request.question, request.language, prepared)
            checked = QuestionResponse.model_validate(result)
            if len(checked.answer) > self.settings.max_answer_chars:
                raise ValueError("Answer exceeds output budget")
            if checked.source.value == "page" and not (
                context.current_chunk.strip()
                or any(chunk.strip() for chunk in context.related_chunks)
            ):
                raise ValueError("Page attribution requires an excerpt")
            return checked
        except (ValidationError, ValueError, TypeError) as exc:
            raise invalid_upstream(exc) from None
