"""Auth API — registration, email verification, login/refresh/logout, /me."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from app.config import settings
from app.dependencies import (
    get_auth_service,
    get_current_user,
    get_system_settings_service,
)
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    RegistrationModePublicResponse,
    ResendVerificationRequest,
    UserPublic,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.services.auth_service import (
    AccountInactiveError,
    AuthService,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InviteInvalidError,
    InviteRequiredError,
    RegistrationClosedError,
    ResendTooSoonError,
    UsernameAlreadyTakenError,
    VerificationCodeExpiredError,
    VerificationCodeInvalidError,
)
from app.services.system_settings_service import SystemSettingsService

router = APIRouter(prefix="/v1/auth", tags=["auth"])
log = structlog.get_logger(__name__)

_REFRESH_COOKIE = "refresh_token"
_REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str, max_age_seconds: int) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        path=_REFRESH_COOKIE_PATH,
        max_age=max_age_seconds,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        path=_REFRESH_COOKIE_PATH,
        samesite="strict",
        secure=settings.app_env == "production",
        httponly=True,
    )


# ---------- Registration ---------------------------------------------------- #


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/hour")
async def register(
    request: Request,  # noqa: ARG001 — required by slowapi to read remote address
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> RegisterResponse:
    try:
        user = await service.register(
            email=payload.email,
            username=payload.username,
            password=payload.password,
            invite_code=payload.invite_code,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email_taken") from exc
    except UsernameAlreadyTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="username_taken"
        ) from exc
    except RegistrationClosedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="registration_closed"
        ) from exc
    except InviteRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invite_code_required"
        ) from exc
    except InviteInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=exc.code
        ) from exc
    return RegisterResponse(user=UserPublic.model_validate(user))


@router.get(
    "/registration-mode", response_model=RegistrationModePublicResponse
)
async def get_registration_mode(
    settings_service: SystemSettingsService = Depends(get_system_settings_service),
) -> RegistrationModePublicResponse:
    """Public — фронт читает чтобы знать, показывать ли поле invite_code."""
    mode = await settings_service.get_registration_mode()
    return RegistrationModePublicResponse(mode=mode.value)


@router.post("/verify-email", response_model=VerifyEmailResponse)
@limiter.limit("10/15minute")
async def verify_email(
    request: Request,  # noqa: ARG001 — required by slowapi
    payload: VerifyEmailRequest,
    service: AuthService = Depends(get_auth_service),
) -> VerifyEmailResponse:
    """Подтверждение email 6-значным кодом.

    Rate-limit 10 попыток за 15 минут на IP. 6-значный код — это 10^6
    комбинаций; без лимита brute-force за TTL=24ч теоретически возможен.
    С лимитом 10/15min — за 24ч максимум 960 попыток на IP, шанс
    угадывания ~0.001%.
    """
    try:
        user = await service.verify_email(payload.user_id, payload.code)
    except VerificationCodeInvalidError as exc:
        raise HTTPException(status_code=400, detail="verification_code_invalid") from exc
    except VerificationCodeExpiredError as exc:
        raise HTTPException(status_code=400, detail="verification_code_expired") from exc
    return VerifyEmailResponse(user=UserPublic.model_validate(user))


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("5/hour")
async def resend_verification(
    request: Request,  # noqa: ARG001 — required by slowapi
    payload: ResendVerificationRequest,
    service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    """Повторная отправка кода. Server-side cooldown в auth_service (1
    мин между кодами) + IP rate-limit 5/час против email-спама."""
    try:
        await service.resend_verification(payload.user_id)
    except ResendTooSoonError as exc:
        raise HTTPException(status_code=429, detail="resend_too_soon") from exc
    return MessageResponse(message="verification_code_resent")


# ---------- Login / refresh / logout --------------------------------------- #


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/15minute")
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> LoginResponse:
    try:
        access_token, refresh_token, user = await service.login(
            email_or_username=payload.email_or_username,
            password=payload.password,
            remember_me=payload.remember_me,
            device_info=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail="invalid_credentials") from exc
    except EmailNotVerifiedError as exc:
        raise HTTPException(status_code=403, detail="email_not_verified") from exc
    except AccountInactiveError as exc:
        raise HTTPException(status_code=403, detail="account_inactive") from exc

    days = 30 if payload.remember_me else settings.jwt_refresh_token_expire_days
    _set_refresh_cookie(response, refresh_token, max_age_seconds=days * 24 * 3600)
    return LoginResponse(access_token=access_token, user=UserPublic.model_validate(user))


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> RefreshResponse:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="missing_refresh_token")
    try:
        access_token, new_refresh, _user = await service.refresh_access_token(
            refresh_token,
            device_info=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
    except InvalidRefreshTokenError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="invalid_refresh_token") from exc

    _set_refresh_cookie(
        response,
        new_refresh,
        max_age_seconds=settings.jwt_refresh_token_expire_days * 24 * 3600,
    )
    return RefreshResponse(access_token=access_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    service: AuthService = Depends(get_auth_service),
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> MessageResponse:
    if refresh_token:
        await service.logout(refresh_token)
    _clear_refresh_cookie(response)
    return MessageResponse(message="logged_out")


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)
