"""Integration tests: registration / resend triggers actual email delivery
through the EmailService queue.

Use FakeEmailSender (in `conftest.py`) — оно перехватывает письма,
которые AuthService формирует через шаблоны и InProcessQueue.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.email_verification import EmailVerification
from tests.integration.conftest import FakeEmailSender


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


async def test_register_sends_verification_email(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_email_sender: FakeEmailSender,
) -> None:
    resp = await client.post("/api/v1/auth/register", json=_payload())
    assert resp.status_code == 201

    assert len(fake_email_sender.sent) == 1
    message = fake_email_sender.sent[0]
    assert message.to == "alice@example.com"
    assert "alice" in message.text

    # Сверим: код в письме совпадает с тем, что лежит в БД.
    async with db_session_factory() as db:
        verification = (
            await db.execute(select(EmailVerification))
        ).scalars().first()
        assert verification.code in message.text


async def test_resend_sends_another_email(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_email_sender: FakeEmailSender,
    monkeypatch,
) -> None:
    # Регистрируем — приходит первое письмо.
    register = await client.post("/api/v1/auth/register", json=_payload())
    user_id = register.json()["user"]["id"]
    assert len(fake_email_sender.sent) == 1

    # Сбрасываем cooldown, чтобы resend сработал сразу.
    from app.services import auth_service as auth_module
    from datetime import timedelta

    monkeypatch.setattr(auth_module, "_RESEND_COOLDOWN", timedelta(seconds=0))

    resp = await client.post(
        "/api/v1/auth/resend-verification", json={"user_id": user_id}
    )
    assert resp.status_code == 200

    assert len(fake_email_sender.sent) == 2
    second = fake_email_sender.sent[1]
    assert second.to == "alice@example.com"
    # Новый код в БД должен совпадать с кодом в письме.
    async with db_session_factory() as db:
        latest_code = (
            (await db.execute(
                select(EmailVerification).order_by(EmailVerification.id.desc())
            )).scalars().first().code
        )
        assert latest_code in second.text
