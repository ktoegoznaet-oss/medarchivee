"""Integration tests: GET /v1/me/export + DELETE /v1/me/account."""

from __future__ import annotations

import io
import json
import zipfile

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.email_verification import EmailVerification
from app.models.user import User


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
) -> str:
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
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "alice@example.com",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    return login.json()["access_token"]


# ----- Export --------------------------------------------------------- #


async def test_export_returns_zip_with_user_json(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.get(
        "/api/v1/me/export",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "medarchive-export" in resp.headers.get("content-disposition", "")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "README.txt" in names
        assert "user.json" in names
        # JSON-файлы пустых разделов всё равно создаются.
        assert "analyses.json" in names
        assert "ai_conversations.json" in names
        assert "tickets.json" in names

        user_data = json.loads(zf.read("user.json"))
        assert user_data["email"] == "alice@example.com"
        assert user_data["username"] == "alice"


async def test_export_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/me/export")
    assert resp.status_code == 401


# ----- Account deletion ---------------------------------------------- #


async def test_delete_account_removes_user(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.request(
        "DELETE",
        "/api/v1/me/account",
        headers={"Authorization": f"Bearer {access}"},
        json={"password": "Str0ng!Password"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "account_deleted"

    async with db_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 0


async def test_delete_account_rejects_wrong_password(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.request(
        "DELETE",
        "/api/v1/me/account",
        headers={"Authorization": f"Bearer {access}"},
        json={"password": "Wr0ng!Password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_password"

    # User должен быть на месте.
    async with db_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 1


async def test_delete_account_notifies_admin(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_admin_notifier,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    fake_admin_notifier.sent.clear()
    await client.request(
        "DELETE",
        "/api/v1/me/account",
        headers={"Authorization": f"Bearer {access}"},
        json={"password": "Str0ng!Password"},
    )
    assert len(fake_admin_notifier.sent) == 1
    assert "удалил свой аккаунт" in fake_admin_notifier.sent[0]
    assert "alice@example.com" in fake_admin_notifier.sent[0]
