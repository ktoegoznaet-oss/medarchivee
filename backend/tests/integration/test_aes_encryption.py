"""End-to-end test: AES-256-GCM активен, реальные медданные шифруются.

Этот тест ВКЛЮЧАЕТ настоящее шифрование (а не identity stub), чтобы
проверить полный flow register → login → encrypted_dek восстанавливается
→ профиль шифруется и расшифровывается корректно.

Остальные тесты используют identity-провайдер (см. conftest), поэтому
они быстрее и не зависят от Argon2id-памяти.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import dependencies
from app.main import app
from app.models.email_verification import EmailVerification
from app.models.user import User
from app.services.encryption_aesgcm import AESGCMEncryptionService
from tests.unit.test_encryption_aesgcm import InMemoryRedis


@pytest.fixture
def aes_service() -> AESGCMEncryptionService:
    return AESGCMEncryptionService(
        redis_keys_client=InMemoryRedis(),
        # Низкие параметры — для скорости тестов.
        memory_kib=8,
        time_cost=1,
        parallelism=1,
    )


@pytest.fixture
def use_aes(aes_service: AESGCMEncryptionService):
    """Подменяет identity-провайдера на настоящий AES для одного теста."""
    app.dependency_overrides[dependencies.get_encryption_service] = (
        lambda: aes_service
    )
    yield aes_service
    app.dependency_overrides.pop(dependencies.get_encryption_service, None)


def _payload() -> dict[str, object]:
    return {
        "email": "alice@example.com",
        "username": "alice",
        "password": "Str0ng!Password",
        "password_confirm": "Str0ng!Password",
        "terms_accepted": True,
        "privacy_accepted": True,
        "medical_disclaimer_accepted": True,
    }


async def _register_verify_login(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
) -> str:
    resp = await client.post("/api/v1/auth/register", json=_payload())
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user"]["id"]
    async with db_session_factory() as db:
        code = (
            await db.execute(
                select(EmailVerification).where(EmailVerification.user_id == user_id)
            )
        ).scalars().first().code
    await client.post(
        "/api/v1/auth/verify-email", json={"user_id": user_id, "code": code}
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice@example.com",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def test_register_creates_encrypted_dek(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    resp = await client.post("/api/v1/auth/register", json=_payload())
    assert resp.status_code == 201
    async with db_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        assert user.encrypted_dek is not None
        # Базовая проверка: encrypted_dek — base64-строка длиной хотя бы
        # как (DEK_hex 64 chars + nonce 12 + tag 16) ~ base64(92 bytes) ≈ 124.
        assert len(user.encrypted_dek) >= 100


async def test_login_recovers_dek_into_redis(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    await _register_verify_login(client, db_session_factory)
    async with db_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        # После логина DEK должен лежать в Redis под user:{id}:dek.
        dek = await use_aes.get_session_key(user_id=user.id, session_id="ignored")
        assert dek is not None
        assert len(dek) == 32


async def test_profile_round_trip_with_aes(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    """Сохраняем профиль, читаем — данные должны вернуться корректно,
    но в БД лежать шифротекст (не plaintext имя пациента)."""
    access = await _register_verify_login(client, db_session_factory)
    headers = {"Authorization": f"Bearer {access}"}

    payload = {
        "first_name": "Алиса",
        "last_name": "Иванова",
        "birth_date": "1990-01-15",
    }
    create = await client.post("/api/v1/profile", headers=headers, json=payload)
    assert create.status_code in (200, 201), create.text

    read = await client.get("/api/v1/profile", headers=headers)
    assert read.status_code == 200
    body = read.json()
    assert body["first_name"] == "Алиса"
    assert body["last_name"] == "Иванова"

    # В БД имя должно быть зашифровано (не plaintext).
    async with db_session_factory() as db:
        from app.models.patient_profile import PatientProfile

        profile = (await db.execute(select(PatientProfile))).scalars().first()
        assert profile.first_name != "Алиса"
        # Шифротекст — base64 base, явно длиннее plaintext.
        assert len(profile.first_name) > len("Алиса")


async def test_wrong_password_does_not_recover_dek(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    # Регистрируем
    reg = await client.post("/api/v1/auth/register", json=_payload())
    user_id = reg.json()["user"]["id"]
    async with db_session_factory() as db:
        code = (
            await db.execute(
                select(EmailVerification).where(EmailVerification.user_id == user_id)
            )
        ).scalars().first().code
    await client.post(
        "/api/v1/auth/verify-email", json={"user_id": user_id, "code": code}
    )

    # Логин с правильным bcrypt-хешем-уровень-выше, но другой пароль —
    # bcrypt не пройдёт, до KEK не дойдём. Это поведение не меняется
    # с AES. Просто проверяем что обычный invalid_credentials работает.
    wrong = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice@example.com",
            "password": "Wr0ng!Password",
            "remember_me": False,
        },
    )
    assert wrong.status_code == 401
