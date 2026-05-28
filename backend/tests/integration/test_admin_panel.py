"""Integration tests for /api/v1/admin/dashboard и /api/v1/admin/users."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.models.email_verification import EmailVerification
from app.models.user import User, UserRole, UserStatus


def _payload(email: str = "alice@example.com", username: str = "alice") -> dict[str, object]:
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
    db_session_factory: async_sessionmaker,
    email: str = "alice@example.com",
    username: str = "alice",
) -> str:
    reg = await client.post("/api/v1/auth/register", json=_payload(email, username))
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
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    return login.json()["access_token"]


async def _admin_token(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    monkeypatch.setattr(settings, "initial_admin_email", "admin@x.com")
    return await _register_verify_login(
        client, db_session_factory, "admin@x.com", "admin"
    )


# ----- Dashboard ------------------------------------------------------ #


async def test_dashboard_returns_counts(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_access = await _admin_token(client, db_session_factory, monkeypatch)
    # Создаём ещё 2 пользователей.
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _register_verify_login(client, db_session_factory, "alice@example.com", "alice")
    await _register_verify_login(client, db_session_factory, "bob@example.com", "bob")

    resp = await client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["users_total"] == 3
    assert body["users_active_7d"] == 3  # все только что логинились
    assert body["users_blocked"] == 0
    assert body["users_new_7d"] == 3
    assert body["tickets_total"] == 0
    assert isinstance(body["activity_by_day"], list)


async def test_dashboard_requires_admin(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    user_access = await _register_verify_login(client, db_session_factory)
    resp = await client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {user_access}"},
    )
    assert resp.status_code == 403


# ----- Users list & management --------------------------------------- #


async def test_users_list_returns_all(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_access = await _admin_token(client, db_session_factory, monkeypatch)
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _register_verify_login(client, db_session_factory, "alice@example.com", "alice")

    resp = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    emails = [u["email"] for u in body["users"]]
    assert "admin@x.com" in emails
    assert "alice@example.com" in emails


async def test_users_search_by_email(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_access = await _admin_token(client, db_session_factory, monkeypatch)
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _register_verify_login(client, db_session_factory, "alice@example.com", "alice")
    await _register_verify_login(client, db_session_factory, "bob@example.com", "bob")

    resp = await client.get(
        "/api/v1/admin/users?search=alice",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["users"][0]["email"] == "alice@example.com"


async def test_admin_can_block_other_user(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_access = await _admin_token(client, db_session_factory, monkeypatch)
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _register_verify_login(client, db_session_factory, "alice@example.com", "alice")

    async with db_session_factory() as db:
        alice = (
            await db.execute(select(User).where(User.email == "alice@example.com"))
        ).scalar_one()

    resp = await client.patch(
        f"/api/v1/admin/users/{alice.id}/status",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"status": "blocked"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "blocked"

    # Alice больше не может залогиниться.
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice@example.com",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert login.status_code == 403  # account_inactive


async def test_admin_cannot_block_self(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_access = await _admin_token(client, db_session_factory, monkeypatch)
    async with db_session_factory() as db:
        admin = (
            await db.execute(select(User).where(User.email == "admin@x.com"))
        ).scalar_one()

    resp = await client.patch(
        f"/api/v1/admin/users/{admin.id}/status",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"status": "blocked"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "cannot_block_self"


async def test_admin_can_promote_user_to_admin(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_access = await _admin_token(client, db_session_factory, monkeypatch)
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _register_verify_login(client, db_session_factory, "alice@example.com", "alice")
    async with db_session_factory() as db:
        alice = (
            await db.execute(select(User).where(User.email == "alice@example.com"))
        ).scalar_one()

    resp = await client.patch(
        f"/api/v1/admin/users/{alice.id}/role",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


async def test_cannot_demote_last_admin(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_access = await _admin_token(client, db_session_factory, monkeypatch)
    async with db_session_factory() as db:
        admin = (
            await db.execute(select(User).where(User.email == "admin@x.com"))
        ).scalar_one()

    resp = await client.patch(
        f"/api/v1/admin/users/{admin.id}/role",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "user"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "last_admin_demotion_forbidden"
