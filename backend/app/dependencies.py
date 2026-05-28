"""FastAPI dependency-injection factories.

Anything that several routers / services need should be wired through here
so we can swap implementations from one place (e.g. encryption provider).
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole
from app.services.ai_providers.factory import AIProviderFactory
from app.services.ai_service import AIService
from app.services.allergies_service import AllergiesService
from app.services.analysis_norms_service import (
    AnalysisNormsService,
    build_analysis_norms_service,
)
from app.services.analysis_service import AnalysisService
from app.services.auth_service import AuthService, InvalidCredentialsError
from app.services.chronic_conditions_service import ChronicConditionsService
from app.services.dictionaries_service import DictionariesService, build_dictionaries_service
from app.services.email import (
    ArqEmailQueue,
    EmailQueue,
    EmailService,
    InProcessQueue,
    LogEmailSender,
    SmtpEmailSender,
    build_default_templates,
)
from app.services.encryption_identity import IdentityEncryptionService
from app.services.encryption_service import EncryptionService
from app.services.family_history_service import FamilyHistoryService
from app.services.admin_telegram import AdminNotifier, NullAdminNotifier
from app.services.admin_telegram.notifier import AdminNotifierProtocol
from app.services.dashboard_service import DashboardService
from app.services.invite_service import InviteService
from app.services.recovery_service import RecoveryService
from app.services.system_settings_service import SystemSettingsService
from app.services.ticket_service import TicketService
from app.services.users_admin_service import UsersAdminService

from pathlib import Path
from app.services.patient_profile_service import PatientProfileService
from app.services.telegram_sender import TelegramSender
from app.services.telegram_service import TelegramService


@lru_cache(maxsize=1)
def _encryption_service_instance() -> EncryptionService:
    provider = settings.encryption_provider
    if provider == "identity":
        return IdentityEncryptionService()
    if provider == "aesgcm":
        # Late import — argon2-cffi / cryptography подтягиваются только
        # когда реально нужны.
        from redis.asyncio import Redis  # noqa: WPS433

        from app.services.encryption_aesgcm import AESGCMEncryptionService

        redis_keys = Redis(
            host=settings.redis_keys_host,
            port=settings.redis_keys_port,
            db=settings.redis_keys_db,
            decode_responses=False,
        )
        return AESGCMEncryptionService(
            redis_keys_client=redis_keys,
            memory_kib=settings.argon2_memory_kib,
            time_cost=settings.argon2_time_cost,
            parallelism=settings.argon2_parallelism,
        )
    raise ValueError(f"Unknown ENCRYPTION_PROVIDER: {provider!r}")


def get_encryption_service() -> EncryptionService:
    """FastAPI dependency yielding the configured `EncryptionService` singleton."""
    return _encryption_service_instance()


def reset_encryption_service_cache() -> None:
    """Clear the cached encryption service.

    Test helper — required because `_encryption_service_instance` is decorated
    with `lru_cache`, so changing `ENCRYPTION_PROVIDER` between tests would
    otherwise return the stale instance.
    """
    _encryption_service_instance.cache_clear()


@lru_cache(maxsize=1)
def _admin_notifier_instance() -> AdminNotifierProtocol:
    if settings.telegram_admin_bot_token and settings.telegram_admin_chat_id:
        return AdminNotifier(
            bot_token=settings.telegram_admin_bot_token,
            chat_id=settings.telegram_admin_chat_id,
        )
    return NullAdminNotifier()


def get_admin_notifier() -> AdminNotifierProtocol:
    return _admin_notifier_instance()


def reset_admin_notifier_cache() -> None:
    _admin_notifier_instance.cache_clear()


@lru_cache(maxsize=1)
def _email_templates_instance():  # type: ignore[no-untyped-def]
    return build_default_templates()


# Pool ARQ инжектируется в state при lifespan-старте FastAPI; до того момента
# (например, в тестах с TestClient без lifespan) фоллбэчимся на InProcessQueue
# с LogEmailSender. Тесты, которые хотят инспектировать письма, переопределяют
# `get_email_service` через `app.dependency_overrides`.
_arq_email_pool_holder: dict[str, object] = {"pool": None}


def set_arq_email_pool(pool: object) -> None:
    _arq_email_pool_holder["pool"] = pool


def reset_arq_email_pool() -> None:
    _arq_email_pool_holder["pool"] = None


def _build_email_queue() -> EmailQueue:
    pool = _arq_email_pool_holder["pool"]
    if pool is not None:
        return ArqEmailQueue(pool)
    if settings.smtp_user:
        return InProcessQueue(
            SmtpEmailSender(
                host=settings.smtp_host,
                port=settings.smtp_port,
                user=settings.smtp_user,
                password=settings.smtp_password,
                from_email=settings.smtp_from_email or settings.smtp_user,
                from_name=settings.smtp_from_name,
                use_ssl=settings.smtp_use_ssl,
                timeout_seconds=settings.smtp_timeout_seconds,
            )
        )
    return InProcessQueue(LogEmailSender())


def get_email_service() -> EmailService:
    return EmailService(
        queue=_build_email_queue(),
        templates=_email_templates_instance(),
        frontend_base_url=settings.frontend_base_url,
    )


def reset_email_templates_cache() -> None:
    _email_templates_instance.cache_clear()


def get_system_settings_service(
    db: AsyncSession = Depends(get_db),
) -> SystemSettingsService:
    return SystemSettingsService(db=db)


def get_invite_service(
    db: AsyncSession = Depends(get_db),
) -> InviteService:
    return InviteService(db=db)


def get_recovery_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
) -> RecoveryService:
    return RecoveryService(db=db, encryption=encryption)


def get_ticket_service(
    db: AsyncSession = Depends(get_db),
    admin_notifier: AdminNotifierProtocol = Depends(get_admin_notifier),
) -> TicketService:
    return TicketService(
        db=db,
        uploads_root=Path(settings.uploads_root),
        admin_notifier=admin_notifier,
    )


def get_dashboard_service(
    db: AsyncSession = Depends(get_db),
) -> DashboardService:
    return DashboardService(db=db, uploads_root=Path(settings.uploads_root))


def get_users_admin_service(
    db: AsyncSession = Depends(get_db),
) -> UsersAdminService:
    return UsersAdminService(db=db)


def get_auth_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
    email_service: EmailService = Depends(get_email_service),
    system_settings: SystemSettingsService = Depends(get_system_settings_service),
    invite_service: InviteService = Depends(get_invite_service),
    admin_notifier: AdminNotifierProtocol = Depends(get_admin_notifier),
) -> AuthService:
    return AuthService(
        db=db,
        encryption=encryption,
        email_service=email_service,
        system_settings=system_settings,
        invite_service=invite_service,
        admin_notifier=admin_notifier,
    )


def get_patient_profile_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
) -> PatientProfileService:
    return PatientProfileService(db=db, encryption=encryption)


def get_chronic_conditions_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
) -> ChronicConditionsService:
    return ChronicConditionsService(db=db, encryption=encryption)


def get_allergies_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
) -> AllergiesService:
    return AllergiesService(db=db, encryption=encryption)


def get_family_history_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
) -> FamilyHistoryService:
    return FamilyHistoryService(db=db, encryption=encryption)


@lru_cache(maxsize=1)
def _dictionaries_service_instance() -> DictionariesService:
    return build_dictionaries_service()


def get_dictionaries_service() -> DictionariesService:
    return _dictionaries_service_instance()


def reset_dictionaries_service_cache() -> None:
    _dictionaries_service_instance.cache_clear()


@lru_cache(maxsize=1)
def _analysis_norms_service_instance() -> AnalysisNormsService:
    return build_analysis_norms_service()


def get_analysis_norms_service() -> AnalysisNormsService:
    return _analysis_norms_service_instance()


def reset_analysis_norms_service_cache() -> None:
    _analysis_norms_service_instance.cache_clear()


def get_analysis_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
    norms: AnalysisNormsService = Depends(get_analysis_norms_service),
) -> AnalysisService:
    return AnalysisService(db=db, encryption=encryption, norms=norms)


@lru_cache(maxsize=1)
def _ai_provider_factory_instance() -> AIProviderFactory:
    return AIProviderFactory(settings)


def get_ai_provider_factory() -> AIProviderFactory:
    return _ai_provider_factory_instance()


def reset_ai_provider_factory_cache() -> None:
    _ai_provider_factory_instance.cache_clear()


def get_ai_service(
    db: AsyncSession = Depends(get_db),
    encryption: EncryptionService = Depends(get_encryption_service),
    provider_factory: AIProviderFactory = Depends(get_ai_provider_factory),
) -> AIService:
    return AIService(
        db=db,
        encryption=encryption,
        provider_factory=provider_factory,
        config=settings,
    )


@lru_cache(maxsize=1)
def _telegram_sender_instance() -> TelegramSender:
    return TelegramSender(bot_token=settings.telegram_bot_token)


def get_telegram_sender() -> TelegramSender:
    return _telegram_sender_instance()


def reset_telegram_sender_cache() -> None:
    _telegram_sender_instance.cache_clear()


def get_telegram_service(
    db: AsyncSession = Depends(get_db),
    sender: TelegramSender = Depends(get_telegram_sender),
) -> TelegramService:
    return TelegramService(
        db=db,
        sender=sender,
        bot_username=settings.telegram_bot_username,
    )


async def get_current_user(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """Resolve the current `User` from the `Authorization: Bearer <jwt>` header."""
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_or_invalid_authorization",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    try:
        return await auth_service.get_user_from_access_token(token)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_access_token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Guard для админских эндпоинтов.

    Поднимает 403 для всех, у кого `role != ADMIN`. Само существование
    эндпоинта не скрывается (в отличие от IDOR на пользовательских данных,
    где мы возвращаем 404): админ-роуты статичны и так известны клиенту,
    нет смысла маскировать их под 404. См. ТЗ §5.4 «Этап 1».
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_required",
        )
    return current_user
