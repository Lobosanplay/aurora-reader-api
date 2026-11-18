import io
import wave

from pydantic import ValidationError

from app.api.errors import APIError, invalid_upstream
from app.core.config import Settings
from app.providers.base import AIProvider
from app.schemas.transcription import TranscriptionResponse


def detected_media_type(data: bytes) -> str | None:
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(data), "rb") as recording:
                if recording.getnframes() > 0 and recording.getcomptype() == "NONE":
                    return "audio/wav"
        except (EOFError, wave.Error):
            pass
    if len(data) >= 27 and data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in data[:128].lower():
        return "audio/webm"
    return None


class TranscriptionService:
    def __init__(self, settings: Settings, provider: AIProvider | None) -> None:
        self.settings = settings
        self.provider = provider

    async def transcribe(
        self, audio: bytes, declared_type: str, language: str | None
    ) -> TranscriptionResponse:
        if not audio:
            raise APIError(400, "INVALID_AUDIO", "Audio is empty.")
        if len(audio) > self.settings.max_audio_bytes:
            raise APIError(413, "PAYLOAD_TOO_LARGE", "Audio exceeds configured limits.")
        actual_type = detected_media_type(audio)
        if actual_type is None or declared_type.split(";", 1)[0].lower() != actual_type:
            raise APIError(415, "UNSUPPORTED_MEDIA_TYPE", "Unsupported audio format.")
        if actual_type == "audio/wav":
            with wave.open(io.BytesIO(audio), "rb") as recording:
                if (
                    recording.getnframes() / recording.getframerate()
                    > self.settings.max_wav_duration_seconds
                ):
                    raise APIError(413, "PAYLOAD_TOO_LARGE", "Audio duration exceeds limit.")
        if self.provider is None:
            raise APIError(503, "PROVIDER_UNAVAILABLE", "Inference provider is not configured.")
        try:
            return TranscriptionResponse.model_validate(
                await self.provider.transcribe(audio, actual_type, language)
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise invalid_upstream(exc) from None
