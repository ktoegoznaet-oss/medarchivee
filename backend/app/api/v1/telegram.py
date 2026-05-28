"""Telegram bot binding REST API (этап 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import get_current_user, get_telegram_service
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.telegram import (
    TelegramBindingCodeResponse,
    TelegramBindingStatus,
    TelegramNotificationSettingsUpdate,
    TelegramTestMessageResponse,
)
from app.services.telegram_service import (
    BindingNotFoundError,
    CodeRateLimitError,
    TelegramService,
)

router = APIRouter(prefix="/v1/telegram", tags=["telegram"])


def _to_status(binding) -> TelegramBindingStatus:  # type: ignore[no-untyped-def]
    if binding is None:
        return TelegramBindingStatus(bound=False)
    return TelegramBindingStatus(
        bound=True,
        telegram_user_id=binding.telegram_user_id,
        telegram_username=binding.telegram_username,
        bound_at=binding.bound_at,
        notifications_enabled=binding.notifications_enabled,
        notify_medications=binding.notify_medications,
        notify_visits=binding.notify_visits,
        notify_daily_summary=binding.notify_daily_summary,
        notify_health_tips=binding.notify_health_tips,
    )


@router.get("/binding", response_model=TelegramBindingStatus)
async def get_binding(
    current_user: User = Depends(get_current_user),
    svc: TelegramService = Depends(get_telegram_service),
) -> TelegramBindingStatus:
    binding = await svc.get_binding(current_user.id)
    return _to_status(binding)


@router.post(
    "/binding/code",
    response_model=TelegramBindingCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def generate_binding_code(
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(get_current_user),
    svc: TelegramService = Depends(get_telegram_service),
) -> TelegramBindingCodeResponse:
    try:
        generated = await svc.generate_binding_code(current_user.id)
    except CodeRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return TelegramBindingCodeResponse(
        code=generated.code,
        expires_at=generated.expires_at,
        bot_username=svc.bot_username,
        deep_link=svc.deep_link(generated.code),
    )


@router.delete("/binding", status_code=status.HTTP_204_NO_CONTENT)
async def delete_binding(
    current_user: User = Depends(get_current_user),
    svc: TelegramService = Depends(get_telegram_service),
) -> None:
    try:
        await svc.unbind(current_user.id)
    except BindingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="binding_not_found") from exc


@router.patch("/binding/notifications", response_model=TelegramBindingStatus)
async def update_notification_settings(
    data: TelegramNotificationSettingsUpdate,
    current_user: User = Depends(get_current_user),
    svc: TelegramService = Depends(get_telegram_service),
) -> TelegramBindingStatus:
    try:
        binding = await svc.update_notification_settings(current_user.id, data)
    except BindingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="binding_not_found") from exc
    return _to_status(binding)


@router.post("/binding/test", response_model=TelegramTestMessageResponse)
async def send_test_message(
    current_user: User = Depends(get_current_user),
    svc: TelegramService = Depends(get_telegram_service),
) -> TelegramTestMessageResponse:
    try:
        delivered = await svc.send_test_message(current_user.id)
    except BindingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="binding_not_found") from exc
    return TelegramTestMessageResponse(delivered=delivered)
