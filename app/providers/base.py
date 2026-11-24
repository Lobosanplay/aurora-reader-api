from typing import Protocol

from app.schemas.question import QuestionResponse
from app.schemas.transcription import TranscriptionResponse
from app.schemas.translation import TranslationChunk


class AIProvider(Protocol):
    async def translate(
        self, chunks: list[TranslationChunk], source_language: str, target_language: str
    ) -> list[TranslationChunk]: ...

    async def answer(self, question: str, language: str, context: str) -> QuestionResponse: ...

    async def transcribe(
        self, audio: bytes, media_type: str, language: str | None
    ) -> TranscriptionResponse: ...


class ManagedAIProvider(AIProvider, Protocol):
    async def close(self) -> None: ...
