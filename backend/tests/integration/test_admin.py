"""Integration tests for admin role + INITIAL_ADMIN_EMAIL bootstrap.

Покрывает:
  * Регистрация с email == INITIAL_ADMIN_EMAIL → role=ADMIN.
  * Регистрация с другим email → role=USER.
  * GET /api/v1/admin/me как USER → 403.
  * GET /api/v1/admin/me как ADMIN → 200.
  * Сравнение email case-insensitive.
  * Пустой INITIAL_ADMIN_EMAIL не назначает админа никому.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.models.email_verification import EmailVerification
from app.models.user import User, UserRole


def _payload(email: str, username: str) -> dict[str, object]:
    return {
        "email": email,
        "username": username,
        "password": "Str0ng!Password",
        "password_confirm": "Str0ng!Password",
        "terms_accepted": True,
        "privacy_accepted": True,
        "medical_disclaimer_accepted": True,
    }


async def _register_verify_login(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    email: str,
    username: str,
) -> str:
    """Register → verify email → login. Returns access token."""
    resp = await client.post("/api/v1/auth/register", json=_payload(email, username))
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user"]["id"]

    async with session_factory() as db:
        result = await db.execute(
            select(EmailVerification).where(EmailVerification.user_id == user_id)
        )
        code = result.scalars().first().code

    verify = await client.post(
        "/api/v1/auth/verify-email", json={"user_id": user_id, "code": code}
    )
    assert verify.status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": email,
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


async def test_initial_admin_email_grants_admin_role(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "boss@example.com")
    await _register_verify_login(
        client, db_session_factory, "boss@example.com", "boss"
    )
    async with db_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        assert user.role == UserRole.ADMIN


async def test_initial_admin_email_case_insensitive(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "  Boss@Example.COM ")
    await _register_verify_login(
        client, db_session_factory, "boss@example.com", "boss"
    )
    async with db_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        assert user.role == UserRole.ADMIN


async def test_other_users_remain_regular(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "boss@example.com")
    await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )
    async with db_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        assert user.role == UserRole.USER


async def test_empty_initial_admin_email_grants_nobody(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )
    async with db_session_factory() as db:
        user = (await db.execute(select(User))).scalars().first()
        assert user.role == UserRole.USER


async def test_admin_endpoint_rejects_regular_user(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    access = await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )
    resp = await client.get(
        "/api/v1/admin/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "admin_required"


async def test_admin_endpoint_returns_admin_user(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "boss@example.com")
    access = await _register_verify_login(
        client, db_session_factory, "boss@example.com", "boss"
    )
    resp = await client.get(
        "/api/v1/admin/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "boss@example.com"
    assert body["role"] == "admin"


async def test_admin_endpoint_requires_authentication(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/admin/me")
    assert resp.status_code == 401
