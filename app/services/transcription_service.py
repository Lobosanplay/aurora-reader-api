import struct

from pydantic import ValidationError

from app.api.errors import APIError, invalid_upstream
from app.core.config import Settings
from app.providers.base import AIProvider
from app.schemas.common import require_supported_language
from app.schemas.transcription import TranscriptionResponse


def wav_duration(data: bytes) -> float:
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise APIError(400, "INVALID_AUDIO", "Malformed WAV recording.")
    if struct.unpack_from("<I", data, 4)[0] != len(data) - 8:
        raise APIError(400, "INVALID_AUDIO", "Malformed WAV recording.")

    offset = 12
    fmt: tuple[int, int, int, int, int, int] | None = None
    data_length: int | None = None
    while offset < len(data):
        if offset + 8 > len(data):
            raise APIError(400, "INVALID_AUDIO", "Malformed WAV recording.")
        name, size = struct.unpack_from("<4sI", data, offset)
        offset += 8
        if offset + size > len(data) or offset + size + (size % 2) > len(data):
            raise APIError(400, "INVALID_AUDIO", "Malformed WAV recording.")
        if name == b"fmt ":
            if fmt is not None or size != 16:
                raise APIError(415, "UNSUPPORTED_MEDIA_TYPE", "Unsupported WAV encoding.")
            fmt = struct.unpack_from("<HHIIHH", data, offset)
        elif name == b"data":
            if data_length is not None or fmt is None:
                raise APIError(400, "INVALID_AUDIO", "Malformed WAV recording.")
            data_length = size
        offset += size + (size % 2)
    if fmt is None or data_length is None or data_length == 0:
        raise APIError(400, "INVALID_AUDIO", "Malformed WAV recording.")
    codec, channels, sample_rate, byte_rate, block_align, bits = fmt
    if codec != 1 or channels not in (1, 2) or bits not in (8, 16, 24, 32):
        raise APIError(415, "UNSUPPORTED_MEDIA_TYPE", "Unsupported WAV encoding.")
    if (
        sample_rate == 0
        or block_align != channels * (bits // 8)
        or byte_rate != sample_rate * block_align
        or data_length % block_align
    ):
        raise APIError(400, "INVALID_AUDIO", "Malformed WAV recording.")
    return data_length / byte_rate


class TranscriptionService:
    def __init__(self, settings: Settings, provider: AIProvider | None) -> None:
        self.settings = settings
        self.provider = provider

    async def transcribe(
        self, audio: bytes, declared_type: str, language: str | None
    ) -> TranscriptionResponse:
        if language is not None:
            require_supported_language(language, self.settings.supported_languages)
            if (
                self.settings.ai_provider == "openai"
                and "-" in language
                and language not in ("zh-CN", "zh-TW", "zh-HK")
            ):
                raise APIError(422, "UNSUPPORTED_LANGUAGE", "Language hint is not supported.")
        if not audio:
            raise APIError(400, "INVALID_AUDIO", "Audio is empty.")
        if len(audio) > self.settings.max_audio_bytes:
            raise APIError(413, "PAYLOAD_TOO_LARGE", "Audio exceeds configured limits.")
        if declared_type.split(";", 1)[0].strip().lower() != "audio/wav":
            raise APIError(415, "UNSUPPORTED_MEDIA_TYPE", "Unsupported audio format.")
        duration = wav_duration(audio)
        if duration > self.settings.max_wav_duration_seconds:
            raise APIError(413, "PAYLOAD_TOO_LARGE", "Audio duration exceeds limit.")
        if self.provider is None:
            raise APIError(503, "PROVIDER_UNAVAILABLE", "Inference provider is not configured.")
        try:
            result = TranscriptionResponse.model_validate(
                await self.provider.transcribe(audio, "audio/wav", language)
            )
            if len(result.text) > self.settings.max_transcript_chars:
                raise ValueError("Transcript exceeds output budget")
            if (
                result.language is not None
                and self.settings.supported_languages
                and result.language not in self.settings.supported_languages
            ):
                raise ValueError("Provider returned unsupported language")
            return result
        except (ValidationError, ValueError, TypeError) as exc:
            raise invalid_upstream(exc) from None
