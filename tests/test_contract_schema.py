"""Protect the proposed v1 contract from accidental route and DTO drift."""

import pytest

from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    ("path", "request_model", "response_model", "content_type"),
    [
        ("/api/v1/translate", "TranslationRequest", "TranslationResponse", "application/json"),
        ("/api/v1/ask", "QuestionRequest", "QuestionResponse", "application/json"),
        (
            "/api/v1/transcribe",
            "Body_transcribe_api_v1_transcribe_post",
            "TranscriptionResponse",
            "multipart/form-data",
        ),
    ],
)
def test_v1_openapi_routes_and_error_envelope(path, request_model, response_model, content_type):
    spec = create_app(Settings()).openapi()
    operation = spec["paths"][path]["post"]
    request = operation["requestBody"]["content"][content_type]["schema"]
    assert request["$ref"] == f"#/components/schemas/{request_model}"
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response["$ref"] == f"#/components/schemas/{response_model}"
    for status in ("413", "422", "429", "502", "503", "504"):
        error = operation["responses"][status]["content"]["application/json"]["schema"]
        assert error["$ref"] == "#/components/schemas/ErrorResponse"


def test_v1_openapi_required_fields_and_source_vocabulary():
    schemas = create_app(Settings()).openapi()["components"]["schemas"]
    assert set(schemas["TranslationRequest"]["required"]) == {
        "source_language",
        "target_language",
        "chunks",
    }
    assert set(schemas["TranslationResponse"]["required"]) == {
        "source_language",
        "target_language",
        "chunks",
    }
    assert set(schemas["TranslationChunk"]["required"]) == {"id", "text"}
    assert set(schemas["QuestionRequest"]["required"]) == {"question", "language", "context"}
    assert set(schemas["QuestionResponse"]["required"]) == {
        "answer",
        "source",
        "context_sufficient",
    }
    assert set(schemas["TranscriptionResponse"]["required"]) == {"text"}
    assert set(schemas["AnswerSource"]["enum"]) == {
        "page",
        "general",
        "insufficient",
        "external",
        "mixed",
    }
    assert set(schemas["ErrorDetail"]["required"]) == {"code", "message", "request_id"}
