"""Tickets API — пользовательские эндпоинты.

POST   /v1/tickets                       — создать тикет (multipart: data + screenshot?)
GET    /v1/tickets/mine                  — список своих тикетов
GET    /v1/tickets/{id}                  — детали + комментарии (без is_internal)
POST   /v1/tickets/{id}/comments         — добавить комментарий
GET    /v1/tickets/{id}/attachments/{aid} — скачать скриншот (проверка owner)

Admin-эндпоинты вынесены в admin.py (см. /v1/admin/tickets/*).
"""

from __future__ import annotations

import json

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.dependencies import get_current_user, get_ticket_service
from app.models.user import User, UserRole
from app.schemas.ticket import (
    CreateCommentRequest,
    CreateTicketRequest,
    TicketCommentOut,
    TicketDetailOut,
    TicketListResponse,
    TicketOut,
)
from app.services.ticket_service import (
    AttachmentTooLargeError,
    AttachmentTypeNotAllowedError,
    TicketNotFoundError,
    TicketService,
)

router = APIRouter(prefix="/v1/tickets", tags=["tickets"])
log = structlog.get_logger(__name__)


def _to_out(ticket, attachments, *, user_email: str | None = None) -> TicketOut:
    return TicketOut(
        id=ticket.id,
        user_id=ticket.user_id,
        user_email=user_email,
        type=ticket.type,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        url=ticket.url,
        user_agent=ticket.user_agent,
        screen_size=ticket.screen_size,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        attachments=[
            {
                "id": a.id,
                "original_filename": a.original_filename,
                "mime_type": a.mime_type,
                "size_bytes": a.size_bytes,
                "created_at": a.created_at,
            }
            for a in attachments
        ],
    )


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    request: Request,  # noqa: ARG001 — будущий rate-limit
    payload: str = Form(..., description="JSON body of CreateTicketRequest"),
    screenshot: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
) -> TicketOut:
    """Создание тикета. Тело — JSON-string в поле `payload`, чтобы можно
    было прикрепить multipart-файл `screenshot` в одном запросе."""
    try:
        data = CreateTicketRequest.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="invalid_payload",
        ) from exc

    ticket = await service.create_ticket(
        user_id=current_user.id,
        ticket_type=data.type,
        title=data.title,
        description=data.description,
        url=data.url,
        user_agent=data.user_agent,
        screen_size=data.screen_size,
    )

    if screenshot is not None and screenshot.filename:
        content = await screenshot.read()
        try:
            await service.add_attachment(
                ticket=ticket,
                original_filename=screenshot.filename,
                mime_type=screenshot.content_type or "application/octet-stream",
                content=content,
            )
        except AttachmentTypeNotAllowedError as exc:
            await service.delete_ticket(ticket)
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="attachment_type_not_allowed",
            ) from exc
        except AttachmentTooLargeError as exc:
            await service.delete_ticket(ticket)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="attachment_too_large",
            ) from exc

    attachments = await service.list_attachments(ticket.id)
    return _to_out(ticket, attachments)


@router.get("/mine", response_model=TicketListResponse)
async def list_my_tickets(
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
) -> TicketListResponse:
    tickets = await service.list_user_tickets(current_user.id)
    result = []
    for t in tickets:
        attachments = await service.list_attachments(t.id)
        result.append(_to_out(t, attachments))
    return TicketListResponse(tickets=result)


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
) -> TicketDetailOut:
    try:
        ticket = await service.get_ticket_for_user(
            ticket_id=ticket_id, user_id=current_user.id
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ticket_not_found"
        ) from exc
    attachments = await service.list_attachments(ticket.id)
    comments = await service.list_comments(
        ticket_id=ticket.id, include_internal=False
    )
    base = _to_out(ticket, attachments).model_dump()
    base["comments"] = [TicketCommentOut.model_validate(c) for c in comments]
    return TicketDetailOut.model_validate(base)


@router.post(
    "/{ticket_id}/comments",
    response_model=TicketCommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    ticket_id: int,
    payload: CreateCommentRequest,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
) -> TicketCommentOut:
    try:
        ticket = await service.get_ticket_for_user(
            ticket_id=ticket_id, user_id=current_user.id
        )
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ticket_not_found"
        ) from exc
    comment = await service.add_comment(
        ticket=ticket,
        author_user_id=current_user.id,
        body=payload.body,
        is_internal=False,  # пользователь не может ставить internal
    )
    return TicketCommentOut.model_validate(comment)


@router.get("/{ticket_id}/attachments/{attachment_id}")
async def download_attachment(
    ticket_id: int,
    attachment_id: int,
    current_user: User = Depends(get_current_user),
    service: TicketService = Depends(get_ticket_service),
) -> FileResponse:
    try:
        attachment, ticket, path = await service.get_attachment(attachment_id)
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_not_found"
        ) from exc
    if ticket.id != ticket_id:
        # Защита от подделки ticket_id в URL (anti-IDOR).
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_not_found"
        )
    is_owner = ticket.user_id == current_user.id
    is_admin = current_user.role == UserRole.ADMIN
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment_not_found"
        )
    return FileResponse(
        path,
        media_type=attachment.mime_type,
        filename=attachment.original_filename,
    )
