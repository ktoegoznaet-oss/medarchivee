"""AI assistant REST API («Иван Иваныч»)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_ai_service, get_current_user
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.ai import (
    AIConversationFull,
    AIConversationSummary,
    AIMessageDTO,
    AIMessageSendRequest,
    AIMessageSendResponse,
    AISettingsResponse,
    AISettingsUpdate,
)
from app.services.ai_service import (
    AIConversationNotFoundError,
    AIProviderUnavailableError,
    AIService,
)

router = APIRouter(prefix="/v1/ai", tags=["ai"])


# ---------- Settings ------------------------------------------------------ #


@router.get("/settings", response_model=AISettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> AISettingsResponse:
    return await svc.get_settings(current_user.id)


@router.patch("/settings", response_model=AISettingsResponse)
async def update_settings(
    data: AISettingsUpdate,
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> AISettingsResponse:
    return await svc.update_settings(current_user.id, data)


# ---------- Conversations ------------------------------------------------- #


@router.get("/conversations", response_model=list[AIConversationSummary])
async def list_conversations(
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> list[AIConversationSummary]:
    return await svc.list_conversations(
        current_user.id, include_archived=include_archived
    )


@router.post(
    "/conversations",
    response_model=AIConversationFull,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> AIConversationFull:
    return await svc.create_conversation(current_user.id)


@router.post(
    "/conversations/{conversation_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> None:
    try:
        await svc.archive_conversation(current_user.id, conversation_id)
    except AIConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="conversation_not_found") from exc


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> None:
    try:
        await svc.delete_conversation(current_user.id, conversation_id)
    except AIConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="conversation_not_found") from exc


# ---------- Messages ------------------------------------------------------ #


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[AIMessageDTO],
)
async def list_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> list[AIMessageDTO]:
    try:
        return await svc.get_conversation_messages(current_user.id, conversation_id)
    except AIConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="conversation_not_found") from exc


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AIMessageSendResponse,
)
@limiter.limit("10/minute")
async def send_message(
    request: Request,  # noqa: ARG001 — required by slowapi to read remote address
    conversation_id: int,
    payload: AIMessageSendRequest,
    current_user: User = Depends(get_current_user),
    svc: AIService = Depends(get_ai_service),
) -> AIMessageSendResponse:
    try:
        return await svc.send_message(
            user_id=current_user.id,
            conversation_id=conversation_id,
            user_message=payload.message,
            attached_data=payload.attached_data,
            override_tone=payload.override_tone,
            override_complexity=payload.override_complexity,
        )
    except AIConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="conversation_not_found") from exc
    except AIProviderUnavailableError as exc:
        code = 429 if exc.retry_after else 503
        raise HTTPException(status_code=code, detail=exc.message) from exc
