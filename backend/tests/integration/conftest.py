"""Integration-test harness.

Uses `sqlite+aiosqlite` so the suite runs in CI without a MariaDB container.
The master prompt allows this on the vertical-slice phase (§8 «Тесты»). When
we add `testcontainers` (≥ stage 7) we will swap the engine here without
touching individual test files.

Bcrypt cost factor is dropped to 4 (the lowest allowed) for the duration of
the suite — это сокращает время прогона на порядок без потери реалистичности
кода (тот же passlib, тот же алгоритм).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import dependencies
from app.database import get_db
from app.main import app
from app.models import Base
from app.models.ai import AIProvider as AIProviderEnum
from app.rate_limit import limiter
from app.services.ai_providers.base import (
    AIMessage as ProviderMessage,
    AIProvider,
    AIResponse,
)
from app.services.admin_telegram import NullAdminNotifier
from app.services.analysis_norms_service import AnalysisNormsService
from app.services.dictionaries_service import DictionariesService
from app.services.email import EmailMessage, EmailSender, EmailService, InProcessQueue
from app.services.email.templates import build_default_templates
from app.services.system_settings_service import SystemSettingsService
from app.services.telegram_sender import TelegramSender
from app.utils import passwords as passwords_module
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    fast_ctx = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    monkeypatch.setattr(passwords_module, "_pwd_context", fast_ctx)


@pytest.fixture(autouse=True)
def _disable_rate_limit() -> None:
    """slowapi mutates global state — disable it so login tests don't 429."""
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture(autouse=True)
def _clear_system_settings_cache() -> None:
    """SystemSettingsService кэширует значения в classvar — сбрасываем между тестами."""
    SystemSettingsService.clear_cache()
    yield
    SystemSettingsService.clear_cache()


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Дефолтный режим регистрации для тестов — open. Это позволяет
        # большинству тестов регистрировать пользователей без инвайт-кодов.
        # Тесты на invite_only / closed явно меняют значение через сервис.
        await conn.execute(
            text(
                "INSERT INTO system_settings (key, value, updated_at) "
                "VALUES ('registration_mode', 'open', '2026-05-20 00:00:00')"
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def db_session(db_session_factory) -> AsyncIterator[AsyncSession]:
    async with db_session_factory() as session:
        yield session


class FakeAIProvider(AIProvider):
    """In-memory provider used by integration tests.

    Records every call so tests can assert (e.g.) that safety-triggered
    messages bypass the provider entirely.
    """

    def __init__(self, response_content: str = "Заглушка ответа Ивана Иваныча") -> None:
        self.calls: list[tuple[str, list[ProviderMessage]]] = []
        self._response_content = response_content
        self.side_effect: BaseException | None = None

    async def generate(
        self,
        system_prompt: str,
        messages: list[ProviderMessage],
        max_tokens: int = 1024,
    ) -> AIResponse:
        self.calls.append((system_prompt, list(messages)))
        if self.side_effect is not None:
            raise self.side_effect
        return AIResponse(
            content=self._response_content,
            tokens_used=50,
            provider="gemini",
            model="test",
        )


class FakeAIProviderFactory:
    def __init__(self, provider: FakeAIProvider) -> None:
        self.provider = provider

    def get(self, _preferred: AIProviderEnum) -> AIProvider:
        return self.provider


class FakeEmailSender:
    """Test double — записывает все отправленные письма для assertions."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class FakeTelegramSender(TelegramSender):
    """Telegram sender that records calls instead of hitting api.telegram.org.

    Унаследован от настоящего TelegramSender, чтобы можно было подменять
    через `app.dependency_overrides[get_telegram_sender]` без MRO-сюрпризов.
    """

    def __init__(self) -> None:  # noqa: D401
        super().__init__(bot_token="test-token")
        self.sent: list[tuple[int, str]] = []
        self.delivery_result: bool = True

    async def send_message(
        self, chat_id: int, text: str, *, parse_mode: str = "HTML"
    ) -> bool:
        self.sent.append((chat_id, text))
        return self.delivery_result


@pytest.fixture
def fake_ai_provider() -> FakeAIProvider:
    return FakeAIProvider()


@pytest.fixture
def fake_telegram_sender() -> FakeTelegramSender:
    return FakeTelegramSender()


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def fake_admin_notifier() -> NullAdminNotifier:
    return NullAdminNotifier()


@pytest.fixture
async def client(
    db_session_factory,
    fake_ai_provider: FakeAIProvider,
    fake_telegram_sender: FakeTelegramSender,
    fake_email_sender: FakeEmailSender,
    fake_admin_notifier: NullAdminNotifier,
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[dependencies.get_dictionaries_service] = (
        lambda: DictionariesService(redis_client=None)
    )
    app.dependency_overrides[dependencies.get_analysis_norms_service] = (
        lambda: AnalysisNormsService(redis_client=None)
    )
    app.dependency_overrides[dependencies.get_ai_provider_factory] = (
        lambda: FakeAIProviderFactory(fake_ai_provider)
    )
    app.dependency_overrides[dependencies.get_telegram_sender] = (
        lambda: fake_telegram_sender
    )
    app.dependency_overrides[dependencies.get_email_service] = (
        lambda: EmailService(
            queue=InProcessQueue(fake_email_sender),
            templates=build_default_templates(),
            frontend_base_url="http://test",
        )
    )
    app.dependency_overrides[dependencies.get_admin_notifier] = (
        lambda: fake_admin_notifier
    )
    dependencies.reset_encryption_service_cache()
    dependencies.reset_dictionaries_service_cache()
    dependencies.reset_analysis_norms_service_cache()
    dependencies.reset_ai_provider_factory_cache()
    dependencies.reset_telegram_sender_cache()
    dependencies.reset_admin_notifier_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(dependencies.get_dictionaries_service, None)
    app.dependency_overrides.pop(dependencies.get_analysis_norms_service, None)
    app.dependency_overrides.pop(dependencies.get_ai_provider_factory, None)
    app.dependency_overrides.pop(dependencies.get_telegram_sender, None)
    app.dependency_overrides.pop(dependencies.get_email_service, None)
    app.dependency_overrides.pop(dependencies.get_admin_notifier, None)
