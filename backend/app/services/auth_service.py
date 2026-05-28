"""Authentication service — registration, verification, login, refresh, logout.

Высокоуровневые правила, которые этот сервис обеспечивает:
  * Уникальность email и username — на уровне БД (UNIQUE) и на уровне сервиса
    (явные проверки до INSERT, чтобы вернуть осмысленные ошибки клиенту).
  * Пароль никогда не покидает сервис в открытом виде — только bcrypt-хеш.
  * Refresh-токены случайны (UUID4), в БД лежит лишь SHA-256 хеш —
    компрометация дампа БД не даёт продлевать сессии.
  * При refresh старая сессия помечается revoked, новая выдаётся (ротация).
  * `encryption_service.store_session_key` вызывается всегда — на этапе 7
    переключение в AES-режим не требует правок этого сервиса.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_verification import EmailVerification
from app.models.user import User, UserRole, UserStatus
from app.models.user_session import UserSession
from app.services.admin_telegram.notifier import (
    AdminNotifierProtocol,
    format_new_registration,
)
from app.services.email import EmailService
from app.services.encryption_service import EncryptionService
from app.services.invite_service import (
    InviteCodeInvalidError,
    InviteService,
)
from app.services.system_settings_service import (
    RegistrationMode,
    SystemSettingsService,
)
from app.utils.jwt import InvalidTokenError, create_access_token, decode_access_token
from app.utils.passwords import hash_password, verify_password

log = structlog.get_logger(__name__)

_VERIFICATION_TTL = timedelta(hours=24)
_RESEND_COOLDOWN = timedelta(minutes=1)
_VERIFICATION_TTL_HOURS = int(_VERIFICATION_TTL.total_seconds() // 3600)


# ---------- Exceptions ----------------------------------------------------- #


class AuthError(Exception):
    """Base class for auth-service errors."""


class EmailAlreadyRegisteredError(AuthError):
    pass


class UsernameAlreadyTakenError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class EmailNotVerifiedError(AuthError):
    pass


class AccountInactiveError(AuthError):
    pass


class VerificationCodeInvalidError(AuthError):
    pass


class VerificationCodeExpiredError(AuthError):
    pass


class ResendTooSoonError(AuthError):
    pass


class InvalidRefreshTokenError(AuthError):
    pass


class RegistrationClosedError(AuthError):
    """Режим регистрации `closed` — никто не может зарегистрироваться."""


class InviteRequiredError(AuthError):
    """Режим `invite_only` — нужен валидный invite_code."""


class InviteInvalidError(AuthError):
    """invite_code не найден / истёк / отозван / уже использован."""

    def __init__(self, code: str = "invite_invalid"):
        self.code = code
        super().__init__(code)


# ---------- Helpers -------------------------------------------------------- #


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _refresh_ttl(remember_me: bool) -> timedelta:
    days = 30 if remember_me else settings.jwt_refresh_token_expire_days
    return timedelta(days=days)


# ---------- Service -------------------------------------------------------- #


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        encryption: EncryptionService,
        email_service: EmailService,
        system_settings: SystemSettingsService,
        invite_service: InviteService,
        admin_notifier: AdminNotifierProtocol,
    ):
        self._db = db
        self._encryption = encryption
        self._email = email_service
        self._settings = system_settings
        self._invites = invite_service
        self._admin_notifier = admin_notifier

    # ---- Registration & verification ------------------------------------- #

    async def register(
        self,
        email: str,
        username: str,
        password: str,
        *,
        invite_code: str | None = None,
    ) -> User:
        # INITIAL_ADMIN_EMAIL: первый пользователь с этим email получает роль
        # ADMIN автоматически. Сравнение case-insensitive. Бутстрап-админ
        # имеет привилегию регистрироваться в любом режиме без инвайт-кода
        # — это нужно для первого запуска приложения.
        bootstrap_email = settings.initial_admin_email.strip().lower()
        is_initial_admin = bool(bootstrap_email) and email.lower() == bootstrap_email
        role = UserRole.ADMIN if is_initial_admin else UserRole.USER

        # Проверка режима регистрации.
        if not is_initial_admin:
            mode = await self._settings.get_registration_mode()
            if mode == RegistrationMode.CLOSED:
                raise RegistrationClosedError()
            if mode == RegistrationMode.INVITE_ONLY:
                if not invite_code:
                    raise InviteRequiredError()
                # Валидируем код — не consume сейчас, иначе при ошибке
                # уникальности email/username код останется неиспользованным
                # и мы получим "потерянные" инвайты. Consume произойдёт ниже
                # после успешного создания пользователя.

        existing = await self._db.execute(
            select(User).where(or_(User.email == email, User.username == username))
        )
        for row in existing.scalars():
            if row.email == email:
                raise EmailAlreadyRegisteredError(email)
            if row.username == username:
                raise UsernameAlreadyTakenError(username)

        encryption_salt = secrets.token_bytes(32)
        # Двухслойная архитектура: DEK — случайные 32 байта (никогда
        # не меняется), KEK — производный от пароля через Argon2id.
        # Шифруем DEK через KEK и храним только результат в БД. На
        # identity-провайдере DEK тоже генерируется, но encrypt/decrypt
        # с KEK — passthrough, encrypted_dek получается тривиальным.
        # См. docs/ENCRYPTION.md.
        dek = secrets.token_bytes(32)
        kek = await self._encryption.derive_user_key(password, encryption_salt)
        encrypted_dek_b64 = await self._encryption.encrypt_with_key(
            dek.hex(), kek
        )
        encrypted_dek_bytes = encrypted_dek_b64.encode("ascii")

        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            encryption_salt=encryption_salt,
            encrypted_dek=encrypted_dek_bytes,
            role=role,
            status=UserStatus.ACTIVE,
            email_verified=False,
        )
        self._db.add(user)
        await self._db.flush()

        # Consume инвайт-кода — только если режим invite_only И не initial_admin.
        # Делаем это после flush() чтобы invite.used_by_user_id ссылался на
        # реально существующий user.id. Если consume фейлит — rollback откатит
        # создание user, что мы и хотим (single-transaction).
        if invite_code and not is_initial_admin:
            try:
                await self._invites.consume(code=invite_code, user_id=user.id)
            except InviteCodeInvalidError as exc:
                raise InviteInvalidError(code=str(exc)) from exc

        code = await self._create_verification_code(user.id)
        await self._db.commit()
        await self._db.refresh(user)

        log.info(
            "auth.user_registered",
            user_id=user.id,
            email=email,
            username=username,
            role=role.value,
        )
        if is_initial_admin:
            log.info("auth.initial_admin_granted", user_id=user.id, email=email)
        # Лог-событие сохраняем для аудита и для тестов, которые перехватывают
        # код из логов вместо подъёма SMTP-fixture.
        log.info("email_verification_code", user_id=user.id, code=code)
        await self._email.send_verification_code(
            to=email,
            code=code,
            username=username,
            ttl_hours=_VERIFICATION_TTL_HOURS,
        )
        await self._admin_notifier.notify(
            format_new_registration(email=email, username=username, role=role.value)
        )
        return user

    async def _create_verification_code(self, user_id: int) -> str:
        code = _generate_verification_code()
        verification = EmailVerification(
            user_id=user_id,
            code=code,
            expires_at=datetime.now(UTC).replace(tzinfo=None) + _VERIFICATION_TTL,
            used=False,
        )
        self._db.add(verification)
        await self._db.flush()
        return code

    async def verify_email(self, user_id: int, code: str) -> User:
        result = await self._db.execute(
            select(EmailVerification)
            .where(
                EmailVerification.user_id == user_id,
                EmailVerification.code == code,
                EmailVerification.used.is_(False),
            )
            .order_by(EmailVerification.id.desc())
        )
        verification = result.scalars().first()
        if verification is None:
            raise VerificationCodeInvalidError()
        if verification.expires_at < datetime.now(UTC).replace(tzinfo=None):
            raise VerificationCodeExpiredError()

        verification.used = True
        user = await self._db.get(User, user_id)
        if user is None:
            raise VerificationCodeInvalidError()
        user.email_verified = True
        await self._db.commit()
        await self._db.refresh(user)
        log.info("auth.email_verified", user_id=user_id)
        return user

    async def resend_verification(self, user_id: int) -> str:
        result = await self._db.execute(
            select(EmailVerification)
            .where(EmailVerification.user_id == user_id)
            .order_by(EmailVerification.id.desc())
        )
        latest = result.scalars().first()
        if latest is not None and (
            datetime.now(UTC).replace(tzinfo=None) - latest.created_at < _RESEND_COOLDOWN
        ):
            raise ResendTooSoonError()
        user = await self._db.get(User, user_id)
        if user is None:
            # Без существующего пользователя resend бессмыслен; не раскрываем
            # факт отсутствия (например, для anti-enumeration).
            raise ResendTooSoonError()
        code = await self._create_verification_code(user_id)
        await self._db.commit()
        log.info("email_verification_code", user_id=user_id, code=code)
        await self._email.send_verification_code(
            to=user.email,
            code=code,
            username=user.username,
            ttl_hours=_VERIFICATION_TTL_HOURS,
        )
        return code

    # ---- Login / refresh / logout ---------------------------------------- #

    async def login(
        self,
        *,
        email_or_username: str,
        password: str,
        remember_me: bool,
        device_info: str | None,
        ip_address: str | None,
    ) -> tuple[str, str, User]:
        result = await self._db.execute(
            select(User).where(
                or_(User.email == email_or_username, User.username == email_or_username)
            )
        )
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()
        if not user.email_verified:
            raise EmailNotVerifiedError(user.id)
        if user.status != UserStatus.ACTIVE:
            raise AccountInactiveError()

        access_token = create_access_token(user.id, user.role.value)
        refresh_token_raw = str(uuid.uuid4())
        refresh_ttl = _refresh_ttl(remember_me)
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(refresh_token_raw),
            device_info=device_info,
            ip_address=ip_address,
            expires_at=datetime.now(UTC).replace(tzinfo=None) + refresh_ttl,
        )
        self._db.add(session)
        await self._db.flush()

        # Двухслойная расшифровка: пароль → KEK → DEK из encrypted_dek.
        # На identity-провайдере encrypted_dek может быть None для legacy-
        # пользователей; тогда падаем на KEK как «DEK» (passthrough всё
        # равно его не использует).
        kek = await self._encryption.derive_user_key(
            password, user.encryption_salt
        )
        dek = kek
        if user.encrypted_dek is not None:
            try:
                dek_hex = await self._encryption.decrypt_with_key(
                    user.encrypted_dek.decode("ascii"), kek
                )
                dek = bytes.fromhex(dek_hex)
            except Exception as exc:  # noqa: BLE001
                # GCM tag mismatch на верном bcrypt-хеше = повреждённый
                # encrypted_dek в БД. Для UX это invalid_credentials.
                log.warning(
                    "auth.dek_decrypt_failed",
                    user_id=user.id,
                    error=str(exc),
                )
                raise InvalidCredentialsError() from exc

        await self._encryption.store_session_key(
            user_id=user.id,
            session_id=str(session.id),
            key=dek,
            ttl_seconds=int(refresh_ttl.total_seconds()),
        )

        user.last_login_at = datetime.now(UTC).replace(tzinfo=None)
        await self._db.commit()
        await self._db.refresh(user)
        log.info(
            "auth.login_succeeded",
            user_id=user.id,
            ip_address=ip_address,
            remember_me=remember_me,
        )
        return access_token, refresh_token_raw, user

    async def refresh_access_token(
        self,
        refresh_token: str,
        *,
        device_info: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, str, User]:
        token_hash = _hash_refresh_token(refresh_token)
        result = await self._db.execute(
            select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        )
        session = result.scalar_one_or_none()
        if (
            session is None
            or session.revoked
            or session.expires_at < datetime.now(UTC).replace(tzinfo=None)
        ):
            raise InvalidRefreshTokenError()

        user = await self._db.get(User, session.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise InvalidRefreshTokenError()

        # Ротация: старая сессия revoked, новая создаётся.
        session.revoked = True
        new_refresh_raw = str(uuid.uuid4())
        # TTL новой сессии — как у старой (остаточный). Это упрощает реализацию
        # remember_me: мы не знаем, был ли он включён, но сохраняем общий TTL.
        ttl_left = session.expires_at - datetime.now(UTC).replace(tzinfo=None)
        new_session = UserSession(
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(new_refresh_raw),
            device_info=device_info or session.device_info,
            ip_address=ip_address or session.ip_address,
            expires_at=datetime.now(UTC).replace(tzinfo=None) + ttl_left,
        )
        self._db.add(new_session)
        # Flush до revoke/store, чтобы у new_session был id.
        await self._db.flush()

        # Переносим DEK на новую сессию с обновлённым TTL. Identity-стаб
        # всегда возвращает свой stub-ключ, AES — реальный DEK или None
        # (если Redis_keys рестартился без persistence).
        existing_key = await self._encryption.get_session_key(
            user_id=user.id, session_id=str(session.id)
        )
        if existing_key is None:
            # Ключ потерян — расшифровка данных невозможна. Требуем
            # полный перелогин. session.revoked=True уже стоит выше,
            # так что повторное использование старого refresh запрещено.
            raise InvalidRefreshTokenError()
        await self._encryption.revoke_session_key(
            user_id=user.id, session_id=str(session.id)
        )
        await self._encryption.store_session_key(
            user_id=user.id,
            session_id=str(new_session.id),
            key=existing_key,
            ttl_seconds=int(ttl_left.total_seconds()),
        )

        await self._db.commit()

        access_token = create_access_token(user.id, user.role.value)
        log.info("auth.token_refreshed", user_id=user.id)
        return access_token, new_refresh_raw, user

    async def logout(self, refresh_token: str) -> None:
        token_hash = _hash_refresh_token(refresh_token)
        result = await self._db.execute(
            select(UserSession).where(UserSession.refresh_token_hash == token_hash)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return  # Идемпотентно: не сообщаем, существовал ли токен.
        session.revoked = True
        await self._encryption.revoke_session_key(
            user_id=session.user_id,
            session_id=str(session.id),
        )
        await self._db.commit()
        log.info("auth.logout", user_id=session.user_id)

    # ---- Access-token resolution ----------------------------------------- #

    async def get_user_from_access_token(self, access_token: str) -> User:
        try:
            payload = decode_access_token(access_token)
        except InvalidTokenError as exc:
            raise InvalidCredentialsError() from exc
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidCredentialsError() from exc
        user = await self._db.get(User, user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise InvalidCredentialsError()
        return user
