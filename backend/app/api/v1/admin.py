"""Admin API — operations available only to users with role=ADMIN."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_admin_user,
    get_dashboard_service,
    get_invite_service,
    get_system_settings_service,
    get_ticket_service,
    get_users_admin_service,
)
from app.models.invite import InviteCode
from app.models.support import TicketStatus, TicketType
from app.models.user import User
from app.schemas.admin import (
    AdminUserOut,
    DashboardStatsOut,
    InviteCreateRequest,
    InviteCreateResponse,
    InviteListResponse,
    InviteOut,
    RegistrationModeOut,
    RegistrationModeUpdate,
    SetUserRoleRequest,
    SetUserStatusRequest,
    SystemLimitsOut,
    SystemLimitsUpdate,
    UserListResponse,
)
from app.schemas.auth import UserPublic
from app.schemas.ticket import (
    AdminCreateCommentRequest,
    TicketCommentOut,
    TicketDetailOut,
    TicketListResponse,
    TicketOut,
    UpdateStatusRequest,
)
from app.services.dashboard_service import DashboardService
from app.services.invite_service import (
    InviteCodeAlreadyUsedError,
    InviteCodeNotFoundError,
    InviteService,
    InviteStatus,
)
from app.services.system_settings_service import (
    AI_DAILY_LIMIT_KEY,
    USER_QUOTA_BYTES_KEY,
    SystemSettingsService,
)
from app.services.ticket_service import TicketNotFoundError, TicketService
from app.services.users_admin_service import (
    CannotBlockSelfError,
    SelfDemotionForbiddenError,
    UserNotFoundError,
    UsersAdminService,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/me", response_model=UserPublic)
async def admin_me(current_admin: User = Depends(get_admin_user)) -> UserPublic:
    """Probe-эндпоинт: 200 если роль=ADMIN, иначе 403."""
    return UserPublic.model_validate(current_admin)


# ---------- Dashboard ------------------------------------------------- #


@router.get("/dashboard", response_model=DashboardStatsOut)
async def dashboard(
    _admin: User = Depends(get_admin_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardStatsOut:
    stats = await service.get_stats()
    return DashboardStatsOut(
        users_total=stats.users_total,
        users_active_7d=stats.users_active_7d,
        users_active_30d=stats.users_active_30d,
        users_blocked=stats.users_blocked,
        users_new_7d=stats.users_new_7d,
        tickets_total=stats.tickets_total,
        tickets_new=stats.tickets_new,
        uploads_size_bytes=stats.uploads_size_bytes,
        activity_by_day=[
            {"date": d.date, "count": d.count} for d in stats.activity_by_day
        ],
    )


# ---------- Users management ------------------------------------------ #


@router.get("/users", response_model=UserListResponse)
async def list_users(
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    _admin: User = Depends(get_admin_user),
    service: UsersAdminService = Depends(get_users_admin_service),
) -> UserListResponse:
    users, total = await service.list_users(search=search, limit=limit, offset=offset)
    return UserListResponse(
        users=[AdminUserOut.model_validate(u) for u in users],
        total=total,
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
async def set_user_status(
    user_id: int,
    payload: SetUserStatusRequest,
    current_admin: User = Depends(get_admin_user),
    service: UsersAdminService = Depends(get_users_admin_service),
) -> AdminUserOut:
    try:
        user = await service.set_status(
            target_user_id=user_id,
            new_status=payload.status,
            actor_user_id=current_admin.id,
        )
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found"
        ) from exc
    except CannotBlockSelfError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cannot_block_self",
        ) from exc
    return AdminUserOut.model_validate(user)


@router.patch("/users/{user_id}/role", response_model=AdminUserOut)
async def set_user_role(
    user_id: int,
    payload: SetUserRoleRequest,
    current_admin: User = Depends(get_admin_user),
    service: UsersAdminService = Depends(get_users_admin_service),
) -> AdminUserOut:
    try:
        user = await service.set_role(
            target_user_id=user_id,
            new_role=payload.role,
            actor_user_id=current_admin.id,
        )
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found"
        ) from exc
    except SelfDemotionForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="last_admin_demotion_forbidden",
        ) from exc
    return AdminUserOut.model_validate(user)


# ---------- Invite codes ---------------------------------------------- #


async def _hydrate_invite(
    invite: InviteCode, status_value: InviteStatus, db: AsyncSession
) -> InviteOut:
    """Дополняет invite email-ом пользователя, который его использовал."""
    used_by_email = None
    if invite.used_by_user_id is not None:
        user = await db.get(User, invite.used_by_user_id)
        if user is not None:
            used_by_email = user.email
    return InviteOut(
        id=invite.id,
        code=invite.code,
        created_by_admin_id=invite.created_by_admin_id,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        used_by_user_id=invite.used_by_user_id,
        used_by_email=used_by_email,
        used_at=invite.used_at,
        revoked_at=invite.revoked_at,
        note=invite.note,
        status=status_value,
    )


@router.post(
    "/invites",
    response_model=InviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    payload: InviteCreateRequest,
    current_admin: User = Depends(get_admin_user),
    service: InviteService = Depends(get_invite_service),
    db: AsyncSession = Depends(get_db),
) -> InviteCreateResponse:
    invite = await service.create_code(admin_id=current_admin.id, note=payload.note)
    return InviteCreateResponse(
        invite=await _hydrate_invite(invite, InviteStatus.ACTIVE, db)
    )


@router.get("/invites", response_model=InviteListResponse)
async def list_invites(
    _admin: User = Depends(get_admin_user),
    service: InviteService = Depends(get_invite_service),
    db: AsyncSession = Depends(get_db),
) -> InviteListResponse:
    pairs = await service.list_codes()
    invites = [await _hydrate_invite(inv, status_value, db) for inv, status_value in pairs]
    return InviteListResponse(invites=invites)


@router.delete("/invites/{invite_id}", response_model=InviteOut)
async def revoke_invite(
    invite_id: int,
    _admin: User = Depends(get_admin_user),
    service: InviteService = Depends(get_invite_service),
    db: AsyncSession = Depends(get_db),
) -> InviteOut:
    try:
        invite = await service.revoke(invite_id)
    except InviteCodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="invite_not_found"
        ) from exc
    except InviteCodeAlreadyUsedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="invite_already_used"
        ) from exc
    return await _hydrate_invite(invite, InviteStatus.REVOKED, db)


# ---------- System settings ------------------------------------------- #


@router.get("/settings/registration-mode", response_model=RegistrationModeOut)
async def get_registration_mode_admin(
    _admin: User = Depends(get_admin_user),
    service: SystemSettingsService = Depends(get_system_settings_service),
) -> RegistrationModeOut:
    mode = await service.get_registration_mode()
    return RegistrationModeOut(mode=mode)


@router.patch("/settings/registration-mode", response_model=RegistrationModeOut)
async def set_registration_mode(
    payload: RegistrationModeUpdate,
    current_admin: User = Depends(get_admin_user),
    service: SystemSettingsService = Depends(get_system_settings_service),
) -> RegistrationModeOut:
    await service.set_registration_mode(
        payload.mode, updated_by_user_id=current_admin.id
    )
    return RegistrationModeOut(mode=payload.mode)


@router.get("/settings/limits", response_model=SystemLimitsOut)
async def get_limits(
    _admin: User = Depends(get_admin_user),
    service: SystemSettingsService = Depends(get_system_settings_service),
) -> SystemLimitsOut:
    return SystemLimitsOut(
        ai_daily_limit=await service.get_ai_daily_limit(),
        user_quota_bytes=await service.get_user_quota_bytes(),
    )


@router.patch("/settings/limits", response_model=SystemLimitsOut)
async def set_limits(
    payload: SystemLimitsUpdate,
    current_admin: User = Depends(get_admin_user),
    service: SystemSettingsService = Depends(get_system_settings_service),
) -> SystemLimitsOut:
    if payload.ai_daily_limit is not None:
        await service.set_value(
            AI_DAILY_LIMIT_KEY,
            str(payload.ai_daily_limit),
            updated_by_user_id=current_admin.id,
        )
    if payload.user_quota_bytes is not None:
        await service.set_value(
            USER_QUOTA_BYTES_KEY,
            str(payload.user_quota_bytes),
            updated_by_user_id=current_admin.id,
        )
    return SystemLimitsOut(
        ai_daily_limit=await service.get_ai_daily_limit(),
        user_quota_bytes=await service.get_user_quota_bytes(),
    )


# ---------- Support tickets ------------------------------------------ #


def _ticket_to_out(ticket, attachments, user_email: str | None = None) -> TicketOut:
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


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    status_filter: TicketStatus | None = None,
    type_filter: TicketType | None = None,
    _admin: User = Depends(get_admin_user),
    service: TicketService = Depends(get_ticket_service),
    db: AsyncSession = Depends(get_db),
) -> TicketListResponse:
    tickets = await service.list_all_tickets(
        status_filter=status_filter, type_filter=type_filter
    )
    result = []
    for ticket in tickets:
        attachments = await service.list_attachments(ticket.id)
        user = await db.get(User, ticket.user_id)
        result.append(
            _ticket_to_out(
                ticket, attachments, user_email=user.email if user else None
            )
        )
    return TicketListResponse(tickets=result)


@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket_admin(
    ticket_id: int,
    _admin: User = Depends(get_admin_user),
    service: TicketService = Depends(get_ticket_service),
    db: AsyncSession = Depends(get_db),
) -> TicketDetailOut:
    try:
        ticket = await service.get_ticket_for_admin(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ticket_not_found"
        ) from exc
    attachments = await service.list_attachments(ticket.id)
    comments = await service.list_comments(
        ticket_id=ticket.id, include_internal=True
    )
    user = await db.get(User, ticket.user_id)
    base = _ticket_to_out(
        ticket, attachments, user_email=user.email if user else None
    ).model_dump()
    base["comments"] = [TicketCommentOut.model_validate(c) for c in comments]
    return TicketDetailOut.model_validate(base)


@router.patch("/tickets/{ticket_id}/status", response_model=TicketOut)
async def set_ticket_status(
    ticket_id: int,
    payload: UpdateStatusRequest,
    _admin: User = Depends(get_admin_user),
    service: TicketService = Depends(get_ticket_service),
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    try:
        ticket = await service.get_ticket_for_admin(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ticket_not_found"
        ) from exc
    await service.update_status(ticket=ticket, status=payload.status)
    attachments = await service.list_attachments(ticket.id)
    user = await db.get(User, ticket.user_id)
    return _ticket_to_out(
        ticket, attachments, user_email=user.email if user else None
    )


@router.post(
    "/tickets/{ticket_id}/comments",
    response_model=TicketCommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_admin_comment(
    ticket_id: int,
    payload: AdminCreateCommentRequest,
    current_admin: User = Depends(get_admin_user),
    service: TicketService = Depends(get_ticket_service),
) -> TicketCommentOut:
    try:
        ticket = await service.get_ticket_for_admin(ticket_id)
    except TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ticket_not_found"
        ) from exc
    comment = await service.add_comment(
        ticket=ticket,
        author_user_id=current_admin.id,
        body=payload.body,
        is_internal=payload.is_internal,
    )
    return TicketCommentOut.model_validate(comment)
