"""Integration tests for /api/v1/telegram/*."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.email_verification import EmailVerification
from app.models.telegram import TelegramBinding, TelegramBindingCode
from app.services.telegram_sender import TelegramSender
from app.services.telegram_service import TelegramService
from tests.integration.conftest import FakeTelegramSender


def _valid_register_payload(**overrides: object) -> dict[str, object]:
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


async def _register_and_login(
    client: AsyncClient,
    factory: async_sessionmaker,
    *,
    email: str = "alice@example.com",
    username: str = "alice",
) -> tuple[int, str]:
    payload = _valid_register_payload(email=email, username=username)
    register = await client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201, register.text
    user_id = register.json()["user"]["id"]

    async with factory() as db:
        code_row = (
            (
                await db.execute(
                    select(EmailVerification).where(
                        EmailVerification.user_id == user_id
                    )
                )
            )
            .scalars()
            .first()
        )
    await client.post(
        "/api/v1/auth/verify-email",
        json={"user_id": user_id, "code": code_row.code},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": email,
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert login.status_code == 200, login.text
    return user_id, login.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------- #
# 1. POST /binding/code → 6-значный код, истекает через ~10 минут
# ---------------------------------------------------------------------------- #
async def test_generate_code_returns_six_digit_with_ttl(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    resp = await client.post("/api/v1/telegram/binding/code", headers=_auth(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"].isdigit() and len(body["code"]) == 6
    expires_at = datetime.fromisoformat(body["expires_at"].replace("Z", ""))
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    delta = expires_at - now_naive
    assert timedelta(minutes=9) <= delta <= timedelta(minutes=10, seconds=5)
    assert body["bot_username"]
    assert body["deep_link"].endswith(body["code"])


# ---------------------------------------------------------------------------- #
# 2. Повторная генерация — старый код становится used
# ---------------------------------------------------------------------------- #
async def test_second_code_invalidates_previous(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    user_id, token = await _register_and_login(client, db_session_factory)
    first = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token)
    )
    assert first.status_code == 201
    first_code = first.json()["code"]
    second = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token)
    )
    assert second.status_code == 201
    assert second.json()["code"] != first_code

    async with db_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(TelegramBindingCode).where(
                        TelegramBindingCode.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        codes_by_value = {r.code: r for r in rows}
        assert codes_by_value[first_code].used is True
        assert codes_by_value[second.json()["code"]].used is False


# ---------------------------------------------------------------------------- #
# 3. GET /binding без привязки → bound:false
# ---------------------------------------------------------------------------- #
async def test_get_binding_unbound(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    resp = await client.get("/api/v1/telegram/binding", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["bound"] is False


# ---------------------------------------------------------------------------- #
# 4. После bind_by_code → GET /binding возвращает данные
# ---------------------------------------------------------------------------- #
async def test_binding_visible_after_bind(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_telegram_sender: FakeTelegramSender,
) -> None:
    user_id, token = await _register_and_login(client, db_session_factory)
    code_resp = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token)
    )
    code = code_resp.json()["code"]

    async with db_session_factory() as db:
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        result = await svc.bind_by_code(
            code=code,
            telegram_user_id=12345,
            telegram_username="@TESTuser",
        )
    assert result.ok is True

    resp = await client.get("/api/v1/telegram/binding", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["bound"] is True
    assert body["telegram_user_id"] == 12345
    # username нормализован — без @ и в нижнем регистре.
    assert body["telegram_username"] == "testuser"


# ---------------------------------------------------------------------------- #
# 5. PATCH /notifications обновляет только переданные поля
# ---------------------------------------------------------------------------- #
async def test_patch_notifications_partial_update(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_telegram_sender: FakeTelegramSender,
) -> None:
    user_id, token = await _register_and_login(client, db_session_factory)
    code_resp = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token)
    )
    async with db_session_factory() as db:
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        await svc.bind_by_code(
            code=code_resp.json()["code"],
            telegram_user_id=999,
            telegram_username="bob",
        )

    patch = await client.patch(
        "/api/v1/telegram/binding/notifications",
        json={"notify_daily_summary": True, "notify_medications": False},
        headers=_auth(token),
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["notify_daily_summary"] is True
    assert body["notify_medications"] is False
    # Поля, которые не передали, остались дефолтными.
    assert body["notify_visits"] is True
    assert body["notifications_enabled"] is True


# ---------------------------------------------------------------------------- #
# 6. DELETE /binding удаляет привязку
# ---------------------------------------------------------------------------- #
async def test_delete_binding(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_telegram_sender: FakeTelegramSender,
) -> None:
    user_id, token = await _register_and_login(client, db_session_factory)
    code_resp = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token)
    )
    async with db_session_factory() as db:
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        await svc.bind_by_code(
            code=code_resp.json()["code"],
            telegram_user_id=555,
            telegram_username="alice",
        )

    resp = await client.delete("/api/v1/telegram/binding", headers=_auth(token))
    assert resp.status_code == 204
    after = await client.get("/api/v1/telegram/binding", headers=_auth(token))
    assert after.json()["bound"] is False

    # Второй DELETE — 404, привязки больше нет.
    again = await client.delete("/api/v1/telegram/binding", headers=_auth(token))
    assert again.status_code == 404


# ---------------------------------------------------------------------------- #
# 7. Bind с истёкшим кодом → 400 (через service-уровень)
# ---------------------------------------------------------------------------- #
async def test_bind_with_expired_code_rejected(
    db_session_factory: async_sessionmaker,
    fake_telegram_sender: FakeTelegramSender,
) -> None:
    # Подложим в БД истёкший код вручную — это удобнее, чем ждать минут.
    async with db_session_factory() as db:
        from app.models.user import User

        user = User(
            email="x@x.x",
            username="x",
            password_hash="x",
            encryption_salt=b"\x00" * 32,
        )
        db.add(user)
        await db.flush()
        db.add(
            TelegramBindingCode(
                user_id=user.id,
                code="000000",
                expires_at=datetime.now(UTC).replace(tzinfo=None)
                - timedelta(seconds=1),
            )
        )
        await db.commit()
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        result = await svc.bind_by_code(
            code="000000",
            telegram_user_id=42,
            telegram_username=None,
        )
    assert result.ok is False
    assert result.error == "code_expired"


# ---------------------------------------------------------------------------- #
# 8. Bind с уже привязанным telegram_user_id (другой пользователь) → reject
# ---------------------------------------------------------------------------- #
async def test_bind_collision_other_user_rejected(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_telegram_sender: FakeTelegramSender,
) -> None:
    # Пользователь A привязывает tg-id=777.
    _, token_a = await _register_and_login(client, db_session_factory)
    code_a = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token_a)
    )
    async with db_session_factory() as db:
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        first = await svc.bind_by_code(
            code=code_a.json()["code"],
            telegram_user_id=777,
            telegram_username=None,
        )
    assert first.ok is True

    # Пользователь B пытается тот же tg-id.
    _, token_b = await _register_and_login(
        client, db_session_factory, email="b@e.e", username="bob"
    )
    code_b = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token_b)
    )
    async with db_session_factory() as db:
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        second = await svc.bind_by_code(
            code=code_b.json()["code"],
            telegram_user_id=777,
            telegram_username=None,
        )
    assert second.ok is False
    assert second.error == "telegram_account_already_bound"


# ---------------------------------------------------------------------------- #
# 9. /binding/test → TelegramSender вызывается с правильным chat_id
# ---------------------------------------------------------------------------- #
async def test_test_message_uses_sender(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_telegram_sender: FakeTelegramSender,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    code_resp = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token)
    )
    async with db_session_factory() as db:
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        await svc.bind_by_code(
            code=code_resp.json()["code"],
            telegram_user_id=4242,
            telegram_username=None,
        )

    test = await client.post("/api/v1/telegram/binding/test", headers=_auth(token))
    assert test.status_code == 200, test.text
    assert test.json()["delivered"] is True
    assert any(chat_id == 4242 for chat_id, _ in fake_telegram_sender.sent)
    # Текст — нейтральный, без чувствительных данных.
    text = fake_telegram_sender.sent[-1][1]
    assert "Тестовое сообщение" in text


# ---------------------------------------------------------------------------- #
# 10. Изоляция: B не видит привязку A
# ---------------------------------------------------------------------------- #
async def test_users_dont_see_each_others_binding(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_telegram_sender: FakeTelegramSender,
) -> None:
    _, token_a = await _register_and_login(client, db_session_factory)
    code_a = await client.post(
        "/api/v1/telegram/binding/code", headers=_auth(token_a)
    )
    async with db_session_factory() as db:
        svc = TelegramService(
            db=db, sender=fake_telegram_sender, bot_username="medarchive_bot"
        )
        await svc.bind_by_code(
            code=code_a.json()["code"],
            telegram_user_id=10001,
            telegram_username="a",
        )

    _, token_b = await _register_and_login(
        client, db_session_factory, email="b@b.b", username="bb"
    )
    resp_b = await client.get("/api/v1/telegram/binding", headers=_auth(token_b))
    assert resp_b.status_code == 200
    assert resp_b.json()["bound"] is False


# ---------------------------------------------------------------------------- #
# 11. TelegramSender реально не вызывает сеть при пустом токене
# ---------------------------------------------------------------------------- #
async def test_sender_returns_false_without_token() -> None:
    sender = TelegramSender(bot_token="")
    ok = await sender.send_message(chat_id=1, text="x")
    assert ok is False
