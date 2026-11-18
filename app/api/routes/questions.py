from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_question_service
from app.schemas.question import QuestionRequest, QuestionResponse
from app.services.question_service import QuestionService

router = APIRouter()


@router.post("/ask", response_model=QuestionResponse)
async def ask(
    request: QuestionRequest,
    service: Annotated[QuestionService, Depends(get_question_service)],
) -> QuestionResponse:
    return await service.answer(request)
