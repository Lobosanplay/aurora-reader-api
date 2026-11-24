import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.question import AnswerSource, QuestionResponse
from app.schemas.transcription import TranscriptionResponse
from app.schemas.translation import TranslationChunk


@pytest.fixture(autouse=True)
def isolate_local_settings_file(monkeypatch):
    # Unit tests must never pick up a developer's ignored .env or paid credentials.
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})


class FakeProvider:
    async def translate(
        self, chunks: list[TranslationChunk], source_language: str, target_language: str
    ) -> list[TranslationChunk]:
        return [TranslationChunk(id=c.id, text=f"Translated: {c.text}") for c in chunks]

    async def answer(self, question: str, language: str, context: str) -> QuestionResponse:
        if not context:
            return QuestionResponse(
                answer="Not enough page context.",
                source=AnswerSource.INSUFFICIENT,
                context_sufficient=False,
            )
        return QuestionResponse(
            answer=f"{language}: {context}", source=AnswerSource.PAGE, context_sufficient=True
        )

    async def transcribe(
        self, audio: bytes, media_type: str, language: str | None
    ) -> TranscriptionResponse:
        return TranscriptionResponse(text="Test transcript", language=language)


@pytest.fixture
def app():
    application = create_app(
        Settings(allowed_origins=["http://localhost:5173", "chrome-extension://abcdefghijklmnop"])
    )
    application.state.provider = FakeProvider()
    return application


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
