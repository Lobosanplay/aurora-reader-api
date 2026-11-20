from pydantic import Field, field_validator, model_validator

from app.schemas.common import StrictModel, validate_language


class TranslationChunk(StrictModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Chunk text must not be blank")
        return value


class TranslationRequest(StrictModel):
    source_language: str
    target_language: str
    chunks: list[TranslationChunk] = Field(min_length=1)

    @field_validator("source_language", "target_language")
    @classmethod
    def language_tag(cls, value: str) -> str:
        return validate_language(value)

    @model_validator(mode="after")
    def unique_ids(self) -> "TranslationRequest":
        ids = [chunk.id for chunk in self.chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate chunk IDs")
        return self


class TranslationResponse(StrictModel):
    source_language: str
    target_language: str
    chunks: list[TranslationChunk]
