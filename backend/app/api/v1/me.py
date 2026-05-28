"""User-facing me-endpoints: экспорт данных и удаление аккаунта (ФЗ-152).

Маршруты:
  GET    /v1/me/export    — стрим ZIP со всеми данными пользователя
  DELETE /v1/me/account   — удалить свой аккаунт (требует пароль)
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import (
    get_admin_notifier,
    get_current_user,
    get_encryption_service,
)
from app.models.user import User
from app.rate_limit import limiter
from app.services.account_deletion_service import (
    AccountDeletionService,
    WrongPasswordError,
)
from app.services.admin_telegram.notifier import AdminNotifierProtocol
from app.services.encryption_service import EncryptionService
from app.services.export_service import ExportService

router = APIRouter(prefix="/v1/me", tags=["me"])
log = structlog.get_logger(__name__)


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    password: str = Field(min_length=1, max_length=200)


class MessageResponse(BaseModel):
    message: str


@router.get("/export")
@limiter.limit("3/hour")
async def export_data(
    request: Request,  # noqa: ARG001 — for slowapi
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
) -> Response:
    service = ExportService(
        db=db,
        encryption=encryption,
        uploads_root=Path(settings.uploads_root),
    )
    zip_bytes = await service.build_zip(current_user)
    filename = f"medarchive-export-{current_user.username}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/account", response_model=MessageResponse)
@limiter.limit("3/hour")
async def delete_account(
    request: Request,  # noqa: ARG001 — for slowapi
    payload: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    admin_notifier: AdminNotifierProtocol = Depends(get_admin_notifier),
) -> MessageResponse:
    service = AccountDeletionService(
        db=db,
        uploads_root=Path(settings.uploads_root),
        admin_notifier=admin_notifier,
    )
    try:
        await service.delete(user=current_user, password=payload.password)
    except WrongPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_password",
        ) from exc
    return MessageResponse(message="account_deleted")
