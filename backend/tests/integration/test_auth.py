"""Integration tests for /api/v1/auth/*.

All tests run against an in-memory SQLite via aiosqlite. The HTTP layer is
exercised through `httpx.ASGITransport` so we don't need a live server.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from structlog.testing import capture_logs

from app.models.email_verification import EmailVerification
from app.models.user import User
from app.models.user_session import UserSession


def _valid_payload(**overrides: object) -> dict[str, object]:
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


async def _register_and_verify(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    **overrides: object,
) -> int:
    """Helper: create a user and mark email_verified=True. Returns user_id."""
    payload = _valid_payload(**overrides)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user"]["id"]

    async with session_factory() as db:
        result = await db.execute(
            select(EmailVerification).where(EmailVerification.user_id == user_id)
        )
        code = result.scalars().first().code

    verify = await client.post(
        "/api/v1/auth/verify-email",
        json={"user_id": user_id, "code": code},
    )
    assert verify.status_code == 200, verify.text
    return user_id


# ---------------------------------------------------------------------------- #
# 1. Регистрация с валидными данными
# ---------------------------------------------------------------------------- #
async def test_register_success_persists_user_and_logs_code(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
) -> None:
    with capture_logs() as logs:
        resp = await client.post("/api/v1/auth/register", json=_valid_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["email_verified"] is False
    # Чувствительные поля никогда не уходят в API.
    assert "password_hash" not in body["user"]
    assert "encryption_salt" not in body["user"]

    async with db_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 1
        assert users[0].email_verified is False
        assert len(users[0].encryption_salt) == 32

    code_events = [e for e in logs if e.get("event") == "email_verification_code"]
    assert len(code_events) == 1
    assert code_events[0]["user_id"] == users[0].id
    assert len(code_events[0]["code"]) == 6


# ---------------------------------------------------------------------------- #
# 2. Слабый пароль
# ---------------------------------------------------------------------------- #
async def test_register_rejects_weak_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json=_valid_payload(password="short", password_confirm="short"),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------- #
# 3. Отсутствует согласие
# ---------------------------------------------------------------------------- #
async def test_register_rejects_missing_consent(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json=_valid_payload(medical_disclaimer_accepted=False),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------- #
# 4. Email уже занят
# ---------------------------------------------------------------------------- #
async def test_register_conflict_on_duplicate_email(client: AsyncClient) -> None:
    first = await client.post("/api/v1/auth/register", json=_valid_payload())
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/register",
        json=_valid_payload(username="alice2"),
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "email_taken"


# ---------------------------------------------------------------------------- #
# 5. Подтверждение email с валидным кодом
# ---------------------------------------------------------------------------- #
async def test_verify_email_with_valid_code(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    user_id = await _register_and_verify(client, db_session_factory)

    async with db_session_factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        assert user.email_verified is True


# ---------------------------------------------------------------------------- #
# 6. Истёкший код
# ---------------------------------------------------------------------------- #
async def test_verify_email_with_expired_code(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    register = await client.post("/api/v1/auth/register", json=_valid_payload())
    user_id = register.json()["user"]["id"]

    async with db_session_factory() as db:
        result = await db.execute(
            select(EmailVerification).where(EmailVerification.user_id == user_id)
        )
        verification = result.scalars().first()
        verification.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=1)
        await db.commit()
        code = verification.code

    resp = await client.post(
        "/api/v1/auth/verify-email",
        json={"user_id": user_id, "code": code},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "verification_code_expired"


# ---------------------------------------------------------------------------- #
# 7. Логин до подтверждения email
# ---------------------------------------------------------------------------- #
async def test_login_blocked_until_email_verified(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=_valid_payload())

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice@example.com",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "email_not_verified"


# ---------------------------------------------------------------------------- #
# 8. Успешный логин: access в теле, refresh в cookie
# ---------------------------------------------------------------------------- #
async def test_login_returns_access_in_body_and_refresh_in_cookie(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    await _register_and_verify(client, db_session_factory)

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "Bearer"
    assert body["user"]["email"] == "alice@example.com"
    assert "refresh_token" in resp.cookies


# ---------------------------------------------------------------------------- #
# 9. Неверный пароль
# ---------------------------------------------------------------------------- #
async def test_login_invalid_credentials(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    await _register_and_verify(client, db_session_factory)

    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice",
            "password": "Wr0ng!Password",
            "remember_me": False,
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_credentials"


# ---------------------------------------------------------------------------- #
# 10. Refresh с ротацией
# ---------------------------------------------------------------------------- #
async def test_refresh_rotates_and_revokes_old_session(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    await _register_and_verify(client, db_session_factory)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    old_cookie = login.cookies["refresh_token"]

    refresh = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refresh_token": old_cookie},
    )
    assert refresh.status_code == 200
    assert refresh.json()["access_token"]
    new_cookie = refresh.cookies["refresh_token"]
    assert new_cookie != old_cookie

    async with db_session_factory() as db:
        sessions = (await db.execute(select(UserSession))).scalars().all()
        assert len(sessions) == 2
        revoked_flags = sorted(s.revoked for s in sessions)
        assert revoked_flags == [False, True]


# ---------------------------------------------------------------------------- #
# 11. Refresh с уже отозванным токеном
# ---------------------------------------------------------------------------- #
async def test_refresh_rejects_revoked_token(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    await _register_and_verify(client, db_session_factory)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    old_cookie = login.cookies["refresh_token"]

    first = await client.post(
        "/api/v1/auth/refresh", cookies={"refresh_token": old_cookie}
    )
    assert first.status_code == 200

    # Старый refresh уже revoked.
    replay = await client.post(
        "/api/v1/auth/refresh", cookies={"refresh_token": old_cookie}
    )
    assert replay.status_code == 401
    assert replay.json()["detail"] == "invalid_refresh_token"


# ---------------------------------------------------------------------------- #
# 12. /me — авторизованный и нет
# ---------------------------------------------------------------------------- #
async def test_me_requires_valid_access_token(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    no_auth = await client.get("/api/v1/auth/me")
    assert no_auth.status_code == 401

    await _register_and_verify(client, db_session_factory)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    access = login.json()["access_token"]

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"
