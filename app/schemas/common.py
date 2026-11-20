import re

from pydantic import BaseModel, ConfigDict, field_validator

LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def validate_language(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected a language tag")
    parts = value.split("-")
    normalized = (
        parts[0].lower() + ("-" + parts[1].upper() if len(parts) == 2 else "")
        if len(parts) <= 2
        else value
    )
    if not LANGUAGE_PATTERN.fullmatch(normalized):
        raise ValueError("Expected a language tag such as en or es-MX")
    return normalized


def require_supported_language(value: str, supported: list[str]) -> None:
    if supported and value not in supported:
        from app.api.errors import APIError

        raise APIError(422, "UNSUPPORTED_LANGUAGE", "Language is not supported.")


class ErrorDetail(StrictModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(StrictModel):
    error: ErrorDetail


class LanguageModel(StrictModel):
    language: str

    @field_validator("language")
    @classmethod
    def valid_language(cls, value: str) -> str:
        return validate_language(value)
