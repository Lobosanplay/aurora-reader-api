from pydantic import Field, field_validator

from app.schemas.common import StrictModel, validate_language


class TranscriptionResponse(StrictModel):
    text: str = Field(min_length=1)
    language: str | None = None

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Transcript must not be blank")
        return value.strip()

    @field_validator("language")
    @classmethod
    def language_tag(cls, value: str | None) -> str | None:
        return validate_language(value) if value is not None else None
