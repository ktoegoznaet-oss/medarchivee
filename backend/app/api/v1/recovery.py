"""Recovery API — BIP39 mnemonic flow + reset password + wipe account.

Маршруты:

  POST /v1/recovery/phrase/generate    (auth)   — сгенерировать фразу
  POST /v1/recovery/phrase/confirm     (auth)   — подтвердить и сохранить
  POST /v1/recovery/phrase/regenerate  (auth)   — обновить фразу (требует пароль)
  GET  /v1/recovery/phrase/status      (auth)   — есть ли recovery_master_key
  POST /v1/recovery/reset-password     (public) — забыл пароль, есть фраза
  POST /v1/recovery/wipe-request       (public) — запросить удаление аккаунта
  POST /v1/recovery/wipe-confirm       (public) — подтвердить удаление кодом

Все public-маршруты под rate-limit'ом, чтобы исключить enumeration и
brute-force кода восстановления.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import (
    get_current_user,
    get_email_service,
    get_encryption_service,
    get_recovery_service,
)
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.recovery import (
    ConfirmPhraseRequest,
    ConfirmWipeRequest,
    GeneratePhraseRequest,
    GeneratePhraseResponse,
    MessageResponse,
    PhraseStatusResponse,
    RegeneratePhraseRequest,
    ResetPasswordRequest,
    WipeAccountRequest,
)
from app.services.email import EmailService
from app.services.encryption_service import (
    EncryptionService,
    SessionKeyNotFoundError,
)
from app.services.recovery_service import (
    PhraseAlreadySetError,
    PhraseConfirmationFailedError,
    PhraseValidationError,
    RecoveryService,
    WipeCodeInvalidError,
)
from app.utils.passwords import verify_password

router = APIRouter(prefix="/v1/recovery", tags=["recovery"])
log = structlog.get_logger(__name__)


# ---- Authenticated phrase management --------------------------------- #


@router.get("/phrase/status", response_model=PhraseStatusResponse)
async def phrase_status(
    current_user: User = Depends(get_current_user),
) -> PhraseStatusResponse:
    return PhraseStatusResponse(
        recovery_phrase_set=current_user.recovery_phrase_set,
        lang=current_user.recovery_phrase_lang,  # type: ignore[arg-type]
    )


@router.post("/phrase/generate", response_model=GeneratePhraseResponse)
async def generate_phrase(
    payload: GeneratePhraseRequest,
    _current_user: User = Depends(get_current_user),
    service: RecoveryService = Depends(get_recovery_service),
) -> GeneratePhraseResponse:
    phrase = service.generate_phrase(payload.lang)
    indices = service.pick_confirmation_indices()
    return GeneratePhraseResponse(
        phrase=phrase,
        lang=payload.lang,
        confirmation_indices=indices,
    )


@router.post("/phrase/confirm", response_model=MessageResponse)
async def confirm_phrase(
    payload: ConfirmPhraseRequest,
    current_user: User = Depends(get_current_user),
    service: RecoveryService = Depends(get_recovery_service),
    encryption: EncryptionService = Depends(get_encryption_service),
) -> MessageResponse:
    # Нужен DEK текущей сессии — берём из Redis_keys.
    dek = await encryption.get_session_key(
        user_id=current_user.id, session_id="any"
    )
    if dek is None:
        # Без активного DEK мы не можем зашифровать его recovery-ключом.
        # Это значит TTL refresh-токена истёк или Redis_keys рестартился.
        raise SessionKeyNotFoundError()

    try:
        await service.confirm_phrase(
            user=current_user,
            phrase=payload.phrase,
            lang=payload.lang,
            dek=dek,
            confirmation_indices=payload.confirmation_indices,
            confirmation_words=payload.confirmation_words,
        )
    except PhraseAlreadySetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="phrase_already_set",
        ) from exc
    except PhraseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="phrase_invalid",
        ) from exc
    except PhraseConfirmationFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="phrase_confirmation_failed",
        ) from exc
    return MessageResponse(message="phrase_saved")


@router.post("/phrase/regenerate", response_model=GeneratePhraseResponse)
@limiter.limit("3/hour")
async def regenerate_phrase(
    request: Request,  # noqa: ARG001 — required by slowapi
    payload: RegeneratePhraseRequest,
    current_user: User = Depends(get_current_user),
    service: RecoveryService = Depends(get_recovery_service),
) -> GeneratePhraseResponse:
    # Подтверждение пароля — защита от подмены фразы через
    # XSS / угнанный access-токен.
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_password",
        )
    phrase = await service.regenerate_phrase(user=current_user)
    indices = service.pick_confirmation_indices()
    from app.services.recovery_service import RecoveryLanguage

    lang = RecoveryLanguage(current_user.recovery_phrase_lang or "russian")
    return GeneratePhraseResponse(
        phrase=phrase,
        lang=lang,
        confirmation_indices=indices,
    )


# ---- Public flows (rate-limited) ------------------------------------- #


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/hour")
async def reset_password(
    request: Request,  # noqa: ARG001
    payload: ResetPasswordRequest,
    service: RecoveryService = Depends(get_recovery_service),
) -> MessageResponse:
    try:
        await service.reset_password(
            email=payload.email,
            phrase=payload.phrase,
            new_password=payload.new_password,
        )
    except PhraseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="phrase_invalid",
        ) from exc
    return MessageResponse(message="password_reset")


@router.post("/wipe-request", response_model=MessageResponse)
@limiter.limit("3/hour")
async def wipe_request(
    request: Request,  # noqa: ARG001
    payload: WipeAccountRequest,
    service: RecoveryService = Depends(get_recovery_service),
    email_service: EmailService = Depends(get_email_service),
) -> MessageResponse:
    result = await service.request_wipe(payload.email)
    # Anti-enumeration: всегда отвечаем 200 + одинаковое сообщение,
    # независимо от того, существует ли email.
    if result is not None:
        user, code = result
        await email_service.send_wipe_code(to=user.email, code=code)
    return MessageResponse(message="wipe_code_sent_if_email_exists")


@router.post("/wipe-confirm", response_model=MessageResponse)
@limiter.limit("5/15minute")
async def wipe_confirm(
    request: Request,  # noqa: ARG001
    payload: ConfirmWipeRequest,
    service: RecoveryService = Depends(get_recovery_service),
) -> MessageResponse:
    try:
        await service.confirm_wipe(email=payload.email, code=payload.code)
    except WipeCodeInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="wipe_code_invalid",
        ) from exc
    return MessageResponse(message="account_wiped")
