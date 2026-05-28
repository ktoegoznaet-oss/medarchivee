"""TicketService — CRUD для тикетов поддержки + работа с attachment'ами.

Файлы attachment'ов лежат в backend/uploads/tickets/{ticket_id}/{uuid}.{ext}.
В БД хранится только метаинфо (filename = uuid, original_filename = name
от пользователя). Имена случайные → нельзя угадать путь и скачать чужие.

Размер файла лимит: 5 МБ на attachment. Проверка делается на API-уровне
через UploadFile.size, потому что нам нужно дать клиенту 413/422 ДО того,
как файл полностью попадёт в memory.
"""

from __future__ import annotations

import secrets
import shutil
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import (
    SupportTicket,
    TicketAttachment,
    TicketComment,
    TicketStatus,
    TicketType,
)
from app.services.admin_telegram.notifier import (
    AdminNotifierProtocol,
    NullAdminNotifier,
    format_new_ticket,
)

log = structlog.get_logger(__name__)

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 МБ


class TicketNotFoundError(Exception):
    pass


class TicketAccessDeniedError(Exception):
    pass


class AttachmentTooLargeError(Exception):
    pass


class AttachmentTypeNotAllowedError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _ext_from_mime(mime: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
    }.get(mime.lower(), "bin")


class TicketService:
    def __init__(
        self,
        db: AsyncSession,
        uploads_root: Path,
        admin_notifier: AdminNotifierProtocol | None = None,
    ):
        self._db = db
        self._uploads_root = uploads_root
        self._admin_notifier = admin_notifier or NullAdminNotifier()

    # ---- User-facing operations ----------------------------------------- #

    async def create_ticket(
        self,
        *,
        user_id: int,
        ticket_type: TicketType,
        title: str,
        description: str,
        url: str | None,
        user_agent: str | None,
        screen_size: str | None,
    ) -> SupportTicket:
        ticket = SupportTicket(
            user_id=user_id,
            type=ticket_type.value,
            title=title,
            description=description,
            status=TicketStatus.NEW.value,
            url=url,
            user_agent=user_agent,
            screen_size=screen_size,
        )
        self._db.add(ticket)
        await self._db.commit()
        await self._db.refresh(ticket)
        log.info(
            "ticket.created",
            ticket_id=ticket.id,
            user_id=user_id,
            ticket_type=ticket_type.value,
        )
        # Уведомляем админа. Резолвим email из БД для красоты сообщения.
        from app.models.user import User as UserModel

        user = await self._db.get(UserModel, user_id)
        await self._admin_notifier.notify(
            format_new_ticket(
                ticket_id=ticket.id,
                user_email=user.email if user else f"user#{user_id}",
                ticket_type=ticket_type.value,
                title=title,
            )
        )
        return ticket

    async def add_attachment(
        self,
        *,
        ticket: SupportTicket,
        original_filename: str,
        mime_type: str,
        content: bytes,
    ) -> TicketAttachment:
        if mime_type.lower() not in ALLOWED_MIME_TYPES:
            raise AttachmentTypeNotAllowedError()
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise AttachmentTooLargeError()

        ticket_dir = self._uploads_root / "tickets" / str(ticket.id)
        ticket_dir.mkdir(parents=True, exist_ok=True)
        # Случайное имя — невозможно угадать путь файла.
        random_name = f"{secrets.token_urlsafe(16)}.{_ext_from_mime(mime_type)}"
        path = ticket_dir / random_name
        path.write_bytes(content)

        attachment = TicketAttachment(
            ticket_id=ticket.id,
            filename=random_name,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=len(content),
        )
        self._db.add(attachment)
        await self._db.commit()
        await self._db.refresh(attachment)
        log.info(
            "ticket.attachment_added",
            ticket_id=ticket.id,
            attachment_id=attachment.id,
            size=len(content),
        )
        return attachment

    async def list_user_tickets(self, user_id: int) -> list[SupportTicket]:
        result = await self._db.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(desc(SupportTicket.updated_at))
        )
        return list(result.scalars())

    async def get_ticket_for_user(
        self, *, ticket_id: int, user_id: int
    ) -> SupportTicket:
        ticket = await self._db.get(SupportTicket, ticket_id)
        if ticket is None or ticket.user_id != user_id:
            # 404 (не 403) — anti-IDOR-disclosure.
            raise TicketNotFoundError()
        return ticket

    async def get_ticket_for_admin(self, ticket_id: int) -> SupportTicket:
        ticket = await self._db.get(SupportTicket, ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        return ticket

    async def list_all_tickets(
        self,
        *,
        status_filter: TicketStatus | None = None,
        type_filter: TicketType | None = None,
    ) -> list[SupportTicket]:
        stmt = select(SupportTicket).order_by(desc(SupportTicket.updated_at))
        if status_filter is not None:
            stmt = stmt.where(SupportTicket.status == status_filter.value)
        if type_filter is not None:
            stmt = stmt.where(SupportTicket.type == type_filter.value)
        result = await self._db.execute(stmt)
        return list(result.scalars())

    async def update_status(
        self, *, ticket: SupportTicket, status: TicketStatus
    ) -> SupportTicket:
        ticket.status = status.value
        ticket.updated_at = _now()
        await self._db.commit()
        await self._db.refresh(ticket)
        log.info("ticket.status_updated", ticket_id=ticket.id, status=status.value)
        return ticket

    # ---- Comments -------------------------------------------------------- #

    async def add_comment(
        self,
        *,
        ticket: SupportTicket,
        author_user_id: int,
        body: str,
        is_internal: bool,
    ) -> TicketComment:
        comment = TicketComment(
            ticket_id=ticket.id,
            author_user_id=author_user_id,
            body=body,
            is_internal=is_internal,
        )
        self._db.add(comment)
        ticket.updated_at = _now()
        await self._db.commit()
        await self._db.refresh(comment)
        log.info(
            "ticket.comment_added",
            ticket_id=ticket.id,
            comment_id=comment.id,
            author_user_id=author_user_id,
            is_internal=is_internal,
        )
        return comment

    async def list_comments(
        self, *, ticket_id: int, include_internal: bool
    ) -> list[TicketComment]:
        stmt = (
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at)
        )
        if not include_internal:
            stmt = stmt.where(TicketComment.is_internal.is_(False))
        result = await self._db.execute(stmt)
        return list(result.scalars())

    # ---- Attachments serving -------------------------------------------- #

    async def get_attachment(
        self, attachment_id: int
    ) -> tuple[TicketAttachment, SupportTicket, Path]:
        attachment = await self._db.get(TicketAttachment, attachment_id)
        if attachment is None:
            raise TicketNotFoundError()
        ticket = await self._db.get(SupportTicket, attachment.ticket_id)
        if ticket is None:
            raise TicketNotFoundError()
        path = (
            self._uploads_root / "tickets" / str(ticket.id) / attachment.filename
        )
        if not path.exists():
            raise TicketNotFoundError()
        return attachment, ticket, path

    async def list_attachments(self, ticket_id: int) -> list[TicketAttachment]:
        result = await self._db.execute(
            select(TicketAttachment)
            .where(TicketAttachment.ticket_id == ticket_id)
            .order_by(TicketAttachment.created_at)
        )
        return list(result.scalars())

    async def delete_ticket(self, ticket: SupportTicket) -> None:
        """Полное удаление тикета — CASCADE снесёт комментарии и attachment'ы
        в БД, а директорию uploads/tickets/{id}/ удалим вручную."""
        ticket_dir = self._uploads_root / "tickets" / str(ticket.id)
        if ticket_dir.exists():
            shutil.rmtree(ticket_dir, ignore_errors=True)
        await self._db.delete(ticket)
        await self._db.commit()
        log.info("ticket.deleted", ticket_id=ticket.id)
