from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_translation_service
from app.schemas.translation import TranslationRequest, TranslationResponse
from app.services.translation_service import TranslationService

router = APIRouter()


@router.post("/translate", response_model=TranslationResponse)
async def translate(
    request: TranslationRequest,
    service: Annotated[TranslationService, Depends(get_translation_service)],
) -> TranslationResponse:
    return await service.translate(request)
