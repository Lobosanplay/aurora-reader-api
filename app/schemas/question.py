from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from app.schemas.common import StrictModel, validate_language


class AnswerSource(StrEnum):
    PAGE = "page"
    GENERAL = "general"
    INSUFFICIENT = "insufficient"
    EXTERNAL = "external"
    MIXED = "mixed"


class QuestionContext(StrictModel):
    title: str = Field(default="", max_length=500)
    current_chunk: str = Field(default="")
    related_chunks: list[str] = Field(default_factory=list)


class QuestionRequest(StrictModel):
    question: str = Field(min_length=1)
    language: str
    context: QuestionContext

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be blank")
        return value

    @field_validator("language")
    @classmethod
    def language_tag(cls, value: str) -> str:
        return validate_language(value)


class QuestionResponse(StrictModel):
    answer: str = Field(min_length=1)
    source: AnswerSource
    context_sufficient: bool

    @model_validator(mode="after")
    def consistent_source(self) -> "QuestionResponse":
        if self.source in (AnswerSource.EXTERNAL, AnswerSource.MIXED):
            raise ValueError("External retrieval is not available")
        if self.context_sufficient != (self.source == AnswerSource.PAGE):
            raise ValueError("Inconsistent answer provenance")
        if not self.answer.strip():
            raise ValueError("Answer must not be blank")
        return self
