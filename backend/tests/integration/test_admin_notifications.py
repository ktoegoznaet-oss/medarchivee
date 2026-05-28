"""Integration tests: backend шлёт уведомления админу при регистрации
и создании тикета. Использует fake_admin_notifier из conftest."""

from __future__ import annotations

import json

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.email_verification import EmailVerification


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


async def test_registration_notifies_admin(
    client: AsyncClient,
    fake_admin_notifier,
) -> None:
    await client.post("/api/v1/auth/register", json=_payload())
    assert len(fake_admin_notifier.sent) == 1
    msg = fake_admin_notifier.sent[0]
    assert "Новая регистрация" in msg
    assert "alice@example.com" in msg


async def test_ticket_creation_notifies_admin(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_admin_notifier,
) -> None:
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

    # Очищаем предыдущие уведомления (была регистрация).
    fake_admin_notifier.sent.clear()

    await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {access}"},
        data={
            "payload": json.dumps(
                {
                    "type": "bug",
                    "title": "Тест-бaг",
                    "description": "не работает кнопка",
                }
            )
        },
    )

    assert len(fake_admin_notifier.sent) == 1
    msg = fake_admin_notifier.sent[0]
    assert "Новый тикет" in msg
    assert "alice@example.com" in msg
    assert "Тест-бaг" in msg
