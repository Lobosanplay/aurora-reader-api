from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import ValidationError

from app.api.dependencies import get_transcription_service
from app.api.errors import APIError
from app.schemas.common import validate_language
from app.schemas.transcription import TranscriptionResponse
from app.services.transcription_service import TranscriptionService

router = APIRouter()


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: Annotated[UploadFile, File()],
    service: Annotated[TranscriptionService, Depends(get_transcription_service)],
    language: Annotated[str | None, Form()] = None,
) -> TranscriptionResponse:
    if language is not None:
        try:
            language = validate_language(language)
        except (ValueError, ValidationError):
            raise APIError(422, "INVALID_INPUT", "Invalid language hint.") from None
    try:
        audio = await file.read(service.settings.max_audio_bytes + 1)
        return await service.transcribe(audio, file.content_type or "", language)
    finally:
        await file.close()
