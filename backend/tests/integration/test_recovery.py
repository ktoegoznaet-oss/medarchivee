"""Integration tests for /api/v1/recovery/* — BIP39 + reset + wipe.

Запускаются с настоящим AES-сервисом (use_aes fixture), потому что
identity-провайдер не использует encrypted_dek и flow recovery теряет
смысл на нём.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import dependencies
from app.main import app
from app.models.account_wipe import AccountWipeCode
from app.models.email_verification import EmailVerification
from app.models.user import User
from app.services.encryption_aesgcm import AESGCMEncryptionService
from tests.integration.conftest import FakeEmailSender
from tests.unit.test_encryption_aesgcm import InMemoryRedis


@pytest.fixture
def aes_service() -> AESGCMEncryptionService:
    return AESGCMEncryptionService(
        redis_keys_client=InMemoryRedis(),
        memory_kib=8,
        time_cost=1,
        parallelism=1,
    )


@pytest.fixture
def use_aes(aes_service: AESGCMEncryptionService):
    app.dependency_overrides[dependencies.get_encryption_service] = (
        lambda: aes_service
    )
    yield aes_service
    app.dependency_overrides.pop(dependencies.get_encryption_service, None)


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "email": "alice@example.com",
        "username": "alice",
        "password": "Str0ng!Password",
        "password_confirm": "Str0ng!Password",
        "terms_accepted": True,
        "privacy_accepted": True,
        "medical_disclaimer_accepted": True,
    }
    base.update(overrides)
    return base


async def _register_verify_login(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    *,
    email: str = "alice@example.com",
    username: str = "alice",
    password: str = "Str0ng!Password",
) -> str:
    """Return access token after register → verify → login."""
    reg = await client.post(
        "/api/v1/auth/register",
        json=_payload(email=email, username=username, password=password,
                      password_confirm=password),
    )
    assert reg.status_code == 201, reg.text
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
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": email,
            "password": password,
            "remember_me": False,
        },
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


# ----- Phrase generation & confirmation ------------------------------ #


async def test_generate_phrase_returns_12_words_and_indices(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.post(
        "/api/v1/recovery/phrase/generate",
        headers={"Authorization": f"Bearer {access}"},
        json={"lang": "russian"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["phrase"].split()) == 12
    assert body["lang"] == "russian"
    assert len(body["confirmation_indices"]) == 3
    assert all(0 <= i < 12 for i in body["confirmation_indices"])


async def test_phrase_status_initially_false(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.get(
        "/api/v1/recovery/phrase/status",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200
    assert resp.json()["recovery_phrase_set"] is False


async def test_confirm_phrase_saves_recovery_master_key(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    headers = {"Authorization": f"Bearer {access}"}

    gen = await client.post(
        "/api/v1/recovery/phrase/generate",
        headers=headers,
        json={"lang": "english"},
    )
    body = gen.json()
    phrase = body["phrase"]
    indices = body["confirmation_indices"]
    words = phrase.split()
    confirmation_words = [words[i] for i in indices]

    confirm = await client.post(
        "/api/v1/recovery/phrase/confirm",
        headers=headers,
        json={
            "phrase": phrase,
            "lang": "english",
            "confirmation_indices": indices,
            "confirmation_words": confirmation_words,
        },
    )
    assert confirm.status_code == 200, confirm.text

    async with db_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        assert user.recovery_phrase_set is True
        assert user.recovery_master_key is not None
        assert user.recovery_phrase_lang == "english"

    status_resp = await client.get(
        "/api/v1/recovery/phrase/status", headers=headers
    )
    assert status_resp.json()["recovery_phrase_set"] is True


async def test_confirm_phrase_fails_on_wrong_words(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    headers = {"Authorization": f"Bearer {access}"}

    gen = await client.post(
        "/api/v1/recovery/phrase/generate", headers=headers, json={"lang": "english"}
    )
    body = gen.json()
    indices = body["confirmation_indices"]

    confirm = await client.post(
        "/api/v1/recovery/phrase/confirm",
        headers=headers,
        json={
            "phrase": body["phrase"],
            "lang": "english",
            "confirmation_indices": indices,
            "confirmation_words": ["wrong", "wrong", "wrong"],
        },
    )
    assert confirm.status_code == 400
    assert confirm.json()["detail"] == "phrase_confirmation_failed"


async def test_confirm_phrase_rejects_invalid_bip39(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.post(
        "/api/v1/recovery/phrase/confirm",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "phrase": "this is not a valid bip39 phrase at all really really",
            "lang": "english",
            "confirmation_indices": [0, 1, 2],
            "confirmation_words": ["this", "is", "not"],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "phrase_invalid"


# ----- Reset password via phrase ------------------------------------- #


async def test_reset_password_via_phrase_round_trip(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    """Full flow: register → save phrase → reset password → login with new password."""
    access = await _register_verify_login(client, db_session_factory)
    headers = {"Authorization": f"Bearer {access}"}

    # 1) Save recovery phrase.
    gen = await client.post(
        "/api/v1/recovery/phrase/generate", headers=headers, json={"lang": "english"}
    )
    phrase = gen.json()["phrase"]
    indices = gen.json()["confirmation_indices"]
    words = phrase.split()
    await client.post(
        "/api/v1/recovery/phrase/confirm",
        headers=headers,
        json={
            "phrase": phrase,
            "lang": "english",
            "confirmation_indices": indices,
            "confirmation_words": [words[i] for i in indices],
        },
    )

    # 2) Reset password (public endpoint).
    new_password = "NewStr0ng!Password"
    reset = await client.post(
        "/api/v1/recovery/reset-password",
        json={
            "email": "alice@example.com",
            "phrase": phrase,
            "new_password": new_password,
            "new_password_confirm": new_password,
        },
    )
    assert reset.status_code == 200, reset.text

    # 3) Login with new password works; old password rejected.
    old = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice@example.com",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert old.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice@example.com",
            "password": new_password,
            "remember_me": False,
        },
    )
    assert new_login.status_code == 200


async def test_reset_password_rejects_wrong_phrase(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    headers = {"Authorization": f"Bearer {access}"}

    gen = await client.post(
        "/api/v1/recovery/phrase/generate", headers=headers, json={"lang": "english"}
    )
    phrase = gen.json()["phrase"]
    indices = gen.json()["confirmation_indices"]
    words = phrase.split()
    await client.post(
        "/api/v1/recovery/phrase/confirm",
        headers=headers,
        json={
            "phrase": phrase,
            "lang": "english",
            "confirmation_indices": indices,
            "confirmation_words": [words[i] for i in indices],
        },
    )

    # Совершенно другая валидная BIP39-фраза (но не наша).
    other_phrase = (
        "abandon abandon abandon abandon abandon abandon "
        "abandon abandon abandon abandon abandon about"
    )
    resp = await client.post(
        "/api/v1/recovery/reset-password",
        json={
            "email": "alice@example.com",
            "phrase": other_phrase,
            "new_password": "AnotherStr0ng!Password",
            "new_password_confirm": "AnotherStr0ng!Password",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "phrase_invalid"


# ----- Wipe account ---------------------------------------------------- #


async def test_wipe_request_sends_code_email(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_email_sender: FakeEmailSender,
    use_aes: AESGCMEncryptionService,
) -> None:
    await _register_verify_login(client, db_session_factory)
    fake_email_sender.sent.clear()

    resp = await client.post(
        "/api/v1/recovery/wipe-request",
        json={"email": "alice@example.com"},
    )
    assert resp.status_code == 200

    assert len(fake_email_sender.sent) == 1
    message = fake_email_sender.sent[0]
    assert message.to == "alice@example.com"
    assert "удаление" in message.text.lower() or "удалени" in message.text.lower()


async def test_wipe_request_anti_enumeration(
    client: AsyncClient,
    use_aes: AESGCMEncryptionService,
) -> None:
    """Несуществующий email — ответ всё равно 200, без раскрытия факта."""
    resp = await client.post(
        "/api/v1/recovery/wipe-request",
        json={"email": "nobody@nowhere.example"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "wipe_code_sent_if_email_exists"


async def test_wipe_confirm_deletes_user(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    await _register_verify_login(client, db_session_factory)

    # Запрос wipe-кода
    await client.post(
        "/api/v1/recovery/wipe-request",
        json={"email": "alice@example.com"},
    )
    async with db_session_factory() as db:
        wipe_code = (
            await db.execute(select(AccountWipeCode))
        ).scalars().first()
        code = wipe_code.code

    confirm = await client.post(
        "/api/v1/recovery/wipe-confirm",
        json={"email": "alice@example.com", "code": code},
    )
    assert confirm.status_code == 200
    assert confirm.json()["message"] == "account_wiped"

    async with db_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 0


async def test_wipe_confirm_rejects_wrong_code(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_aes: AESGCMEncryptionService,
) -> None:
    await _register_verify_login(client, db_session_factory)
    resp = await client.post(
        "/api/v1/recovery/wipe-confirm",
        json={"email": "alice@example.com", "code": "00000000"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "wipe_code_invalid"
