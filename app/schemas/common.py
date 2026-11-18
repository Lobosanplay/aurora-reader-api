import re

from pydantic import BaseModel, ConfigDict, field_validator

LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def validate_language(value: str) -> str:
    if not LANGUAGE_PATTERN.fullmatch(value):
        raise ValueError("Expected a language tag such as en or es-MX")
    return value


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
