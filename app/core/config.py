from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_provider: Literal["unconfigured"] = "unconfigured"
    allowed_origins: list[str] = ["http://localhost:5173"]
    max_chunk_length: int = Field(4000, ge=1, le=100_000)
    max_chunks: int = Field(20, ge=1, le=100)
    max_translation_chars: int = Field(20_000, ge=1, le=1_000_000)
    max_question_length: int = Field(1000, ge=1, le=20_000)
    max_context_chars: int = Field(12_000, ge=1, le=100_000)
    max_related_chunks: int = Field(5, ge=0, le=50)
    max_audio_bytes: int = Field(5_000_000, ge=1, le=25_000_000)
    max_wav_duration_seconds: int = Field(60, ge=1, le=600)
    max_json_bytes: int = Field(100_000, ge=1024, le=2_000_000)
    ai_request_timeout_seconds: float = Field(30, gt=0, le=120)
    max_response_tokens: int = Field(600, ge=1, le=4096)
    max_concurrent_provider_requests: int = Field(4, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
