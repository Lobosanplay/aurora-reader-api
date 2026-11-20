from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.common import validate_language


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_provider: Literal["unconfigured", "openai"] = "unconfigured"
    openai_api_key: SecretStr | None = None
    openai_text_model: str = Field("gpt-6.1-terra", min_length=1)
    openai_transcription_model: str = Field("gpt-transcribe", min_length=1)
    deployment_mode: Literal["local", "production"] = "local"
    trusted_gateway_enabled: bool = False
    api_access_key: SecretStr | None = None
    allowed_origins: list[str] = ["http://localhost:5173"]
    supported_languages: list[str] = []
    requests_per_window: int = Field(60, ge=1, le=10_000)
    rate_window_seconds: int = Field(60, ge=1, le=3600)
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
    max_answer_chars: int = Field(2000, ge=1, le=20_000)
    max_transcript_chars: int = Field(4000, ge=1, le=50_000)
    max_concurrent_provider_requests: int = Field(4, ge=1, le=100)

    @model_validator(mode="after")
    def deployment_safety(self) -> "Settings":
        if not self.openai_text_model.strip() or not self.openai_transcription_model.strip():
            raise ValueError("Model names must not be blank")
        self.supported_languages = [validate_language(tag) for tag in self.supported_languages]
        if len(set(self.supported_languages)) != len(self.supported_languages):
            raise ValueError("Duplicate supported languages")
        if self.deployment_mode == "production":
            if (
                not self.trusted_gateway_enabled
                or self.api_access_key is None
                or len(self.api_access_key.get_secret_value()) < 32
            ):
                raise ValueError(
                    "Production requires a trusted gateway and a 32-character access key"
                )
            if not self.allowed_origins or any(
                origin == "*" or origin.startswith("http://") for origin in self.allowed_origins
            ):
                raise ValueError("Production requires explicit secure browser origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
