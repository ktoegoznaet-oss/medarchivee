"""Integration tests for invite codes and registration modes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.models.email_verification import EmailVerification
from app.models.invite import InviteCode


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


async def _set_mode(db_session_factory, mode: str) -> None:
    async with db_session_factory() as db:
        await db.execute(
            text(
                "UPDATE system_settings SET value = :v "
                "WHERE key = 'registration_mode'"
            ),
            {"v": mode},
        )
        await db.commit()


async def _login_admin(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Regs INITIAL_ADMIN_EMAIL=admin@x.com, verifies, returns access token."""
    monkeypatch.setattr(settings, "initial_admin_email", "admin@example.com")
    reg = await client.post(
        "/api/v1/auth/register",
        json=_payload(email="admin@example.com", username="admin"),
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
        "/api/v1/auth/verify-email",
        json={"user_id": user_id, "code": code},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email_or_username": "admin@example.com",
            "password": "Str0ng!Password",
            "remember_me": False,
        },
    )
    assert login.status_code == 200
    return login.json()["access_token"]


# ----- Registration mode endpoint (public) --------------------------- #


async def test_public_registration_mode_returns_current_mode(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/auth/registration-mode")
    assert resp.status_code == 200
    # Дефолт в тестах — open (см. conftest).
    assert resp.json()["mode"] == "open"


# ----- Registration in closed mode ----------------------------------- #


async def test_registration_blocked_in_closed_mode(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _set_mode(db_session_factory, "closed")
    resp = await client.post("/api/v1/auth/register", json=_payload())
    assert resp.status_code == 403
    assert resp.json()["detail"] == "registration_closed"


# ----- Registration in invite_only mode ------------------------------ #


async def test_registration_requires_invite_in_invite_only_mode(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _set_mode(db_session_factory, "invite_only")
    resp = await client.post("/api/v1/auth/register", json=_payload())
    assert resp.status_code == 403
    assert resp.json()["detail"] == "invite_code_required"


async def test_registration_rejects_invalid_invite(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    await _set_mode(db_session_factory, "invite_only")
    resp = await client.post(
        "/api/v1/auth/register",
        json=_payload(invite_code="NONEXISTENTCODE12345"),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("invite_")


async def test_registration_consumes_valid_invite(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Сначала бутстрап-админ создаёт инвайт.
    access = await _login_admin(client, db_session_factory, monkeypatch)
    create = await client.post(
        "/api/v1/admin/invites",
        headers={"Authorization": f"Bearer {access}"},
        json={"note": "alpha tester"},
    )
    assert create.status_code == 201
    code = create.json()["invite"]["code"]
    invite_id = create.json()["invite"]["id"]

    await _set_mode(db_session_factory, "invite_only")

    resp = await client.post(
        "/api/v1/auth/register",
        json=_payload(invite_code=code),
    )
    assert resp.status_code == 201

    # Код помечен использованным.
    async with db_session_factory() as db:
        invite = await db.get(InviteCode, invite_id)
        assert invite.used_by_user_id is not None
        assert invite.used_at is not None


async def test_registration_rejects_already_used_invite(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = await _login_admin(client, db_session_factory, monkeypatch)
    create = await client.post(
        "/api/v1/admin/invites",
        headers={"Authorization": f"Bearer {access}"},
        json={},
    )
    code = create.json()["invite"]["code"]

    await _set_mode(db_session_factory, "invite_only")

    first = await client.post(
        "/api/v1/auth/register",
        json=_payload(email="bob@example.com", username="bob", invite_code=code),
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/register",
        json=_payload(email="carol@example.com", username="carol", invite_code=code),
    )
    assert second.status_code == 400
    assert second.json()["detail"] == "invite_used"


async def test_registration_rejects_expired_invite(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = await _login_admin(client, db_session_factory, monkeypatch)
    create = await client.post(
        "/api/v1/admin/invites",
        headers={"Authorization": f"Bearer {access}"},
        json={},
    )
    code = create.json()["invite"]["code"]
    invite_id = create.json()["invite"]["id"]

    # «Состариваем» инвайт.
    async with db_session_factory() as db:
        invite = await db.get(InviteCode, invite_id)
        invite.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        await db.commit()

    await _set_mode(db_session_factory, "invite_only")

    resp = await client.post(
        "/api/v1/auth/register",
        json=_payload(invite_code=code),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invite_expired"


async def test_initial_admin_can_register_without_invite_in_invite_only(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "boss@example.com")
    await _set_mode(db_session_factory, "invite_only")

    resp = await client.post(
        "/api/v1/auth/register",
        json=_payload(email="boss@example.com", username="boss"),
    )
    assert resp.status_code == 201
    assert resp.json()["user"]["role"] == "admin"


# ----- Admin endpoints ------------------------------------------------ #


async def test_admin_can_create_list_and_revoke_invite(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = await _login_admin(client, db_session_factory, monkeypatch)
    headers = {"Authorization": f"Bearer {access}"}

    # Create
    create = await client.post(
        "/api/v1/admin/invites", headers=headers, json={"note": "tester-1"}
    )
    assert create.status_code == 201
    invite = create.json()["invite"]
    assert invite["status"] == "active"
    assert len(invite["code"]) >= 16
    assert invite["note"] == "tester-1"

    # List
    listing = await client.get("/api/v1/admin/invites", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()["invites"]) == 1

    # Revoke
    revoke = await client.delete(
        f"/api/v1/admin/invites/{invite['id']}", headers=headers
    )
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"


async def test_revoked_invite_rejected_at_registration(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = await _login_admin(client, db_session_factory, monkeypatch)
    create = await client.post(
        "/api/v1/admin/invites",
        headers={"Authorization": f"Bearer {access}"},
        json={},
    )
    invite_id = create.json()["invite"]["id"]
    code = create.json()["invite"]["code"]

    await client.delete(
        f"/api/v1/admin/invites/{invite_id}",
        headers={"Authorization": f"Bearer {access}"},
    )
    await _set_mode(db_session_factory, "invite_only")

    resp = await client.post(
        "/api/v1/auth/register",
        json=_payload(invite_code=code),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invite_revoked"


async def test_non_admin_cannot_create_invite(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Регистрируем обычного юзера и пробуем создать инвайт.
    monkeypatch.setattr(settings, "initial_admin_email", "")
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
    access = login.json()["access_token"]

    resp = await client.post(
        "/api/v1/admin/invites",
        headers={"Authorization": f"Bearer {access}"},
        json={},
    )
    assert resp.status_code == 403


async def test_admin_can_change_registration_mode(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = await _login_admin(client, db_session_factory, monkeypatch)
    headers = {"Authorization": f"Bearer {access}"}

    resp = await client.patch(
        "/api/v1/admin/settings/registration-mode",
        headers=headers,
        json={"mode": "closed"},
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "closed"

    get_resp = await client.get(
        "/api/v1/admin/settings/registration-mode", headers=headers
    )
    assert get_resp.json()["mode"] == "closed"
