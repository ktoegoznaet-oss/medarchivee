"""Integration tests for /api/v1/ai/*."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.email_verification import EmailVerification
from app.services.ai_providers.base import AIServiceUnavailableError
from tests.integration.conftest import FakeAIProvider


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
        verification = (
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
        code = verification.code

    await client.post(
        "/api/v1/auth/verify-email",
        json={"user_id": user_id, "code": code},
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


async def _create_conversation(client: AsyncClient, token: str) -> int:
    resp = await client.post("/api/v1/ai/conversations", headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------- #
# 1. Defaults для /ai/settings
# ---------------------------------------------------------------------------- #
async def test_get_settings_returns_defaults(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    resp = await client.get("/api/v1/ai/settings", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["preferred_provider"] == "gemini"
    assert body["complexity_level"] == "family_doctor"
    assert body["tone"] == "good_friend"
    assert body["data_access_mode"] == "manual"


# ---------------------------------------------------------------------------- #
# 2. PATCH /ai/settings обновляет тон и сложность
# ---------------------------------------------------------------------------- #
async def test_patch_settings_updates_fields(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    resp = await client.patch(
        "/api/v1/ai/settings",
        json={"tone": "professional", "complexity_level": "professor"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tone"] == "professional"
    assert body["complexity_level"] == "professor"
    # Поля, которые не передали, не меняются.
    assert body["data_access_mode"] == "manual"


# ---------------------------------------------------------------------------- #
# 3. POST /ai/conversations создаёт беседу с пустым title
# ---------------------------------------------------------------------------- #
async def test_create_conversation_starts_with_empty_title(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    resp = await client.post("/api/v1/ai/conversations", headers=_auth(token))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == ""
    assert body["is_archived"] is False


# ---------------------------------------------------------------------------- #
# 4. POST сообщения «Привет» → создаются user+assistant сообщения
# ---------------------------------------------------------------------------- #
async def test_send_normal_message_calls_provider(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_ai_provider: FakeAIProvider,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    conv_id = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/ai/conversations/{conv_id}/messages",
        json={"message": "Привет, как ты?"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_message"]["role"] == "user"
    assert body["user_message"]["content"] == "Привет, как ты?"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"] == "Заглушка ответа Ивана Иваныча"
    assert body["assistant_message"]["safety_event_type"] is None
    assert len(fake_ai_provider.calls) == 1
    # Title — первые 50 символов первого user-сообщения.
    assert body["conversation"]["title"] == "Привет, как ты?"


# ---------------------------------------------------------------------------- #
# 5. Suicide-risk: канонический ответ, провайдер НЕ вызывается
# ---------------------------------------------------------------------------- #
async def test_suicide_risk_message_returns_canned_response(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_ai_provider: FakeAIProvider,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    conv_id = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/ai/conversations/{conv_id}/messages",
        json={"message": "не хочу больше жить"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assistant = body["assistant_message"]
    assert assistant["safety_event_type"] == "suicide_risk"
    assert "8-800-2000-122" in assistant["content"]
    # Главное — Gemini не вызвался.
    assert fake_ai_provider.calls == []


# ---------------------------------------------------------------------------- #
# 6. Medical emergency: канонический ответ
# ---------------------------------------------------------------------------- #
async def test_medical_emergency_returns_canned_response(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_ai_provider: FakeAIProvider,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    conv_id = await _create_conversation(client, token)

    resp = await client.post(
        f"/api/v1/ai/conversations/{conv_id}/messages",
        json={"message": "У меня боль в груди, не могу дышать"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assistant = resp.json()["assistant_message"]
    assert assistant["safety_event_type"] == "medical_emergency"
    assert "103" in assistant["content"]
    assert fake_ai_provider.calls == []


# ---------------------------------------------------------------------------- #
# 7. Изоляция: пользователь A не видит беседы B
# ---------------------------------------------------------------------------- #
async def test_users_cannot_see_each_others_conversations(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token_a = await _register_and_login(client, db_session_factory)
    conv_a = await _create_conversation(client, token_a)

    _, token_b = await _register_and_login(
        client, db_session_factory, email="bob@example.com", username="bob"
    )

    # B не видит беседу A в своём списке.
    listed = await client.get("/api/v1/ai/conversations", headers=_auth(token_b))
    assert listed.status_code == 200
    assert all(c["id"] != conv_a for c in listed.json())

    # И не может прочитать её сообщения.
    msg_resp = await client.get(
        f"/api/v1/ai/conversations/{conv_a}/messages", headers=_auth(token_b)
    )
    assert msg_resp.status_code == 404


# ---------------------------------------------------------------------------- #
# 8. Override tone/complexity передаются в провайдер, settings не меняются
# ---------------------------------------------------------------------------- #
async def test_override_tone_does_not_persist(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_ai_provider: FakeAIProvider,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    conv_id = await _create_conversation(client, token)

    await client.post(
        f"/api/v1/ai/conversations/{conv_id}/messages",
        json={
            "message": "Расскажи про холестерин",
            "override_tone": "encyclopedia",
            "override_complexity": "dry_facts",
        },
        headers=_auth(token),
    )
    # Override применился к system prompt этого запроса.
    assert len(fake_ai_provider.calls) == 1
    system_prompt = fake_ai_provider.calls[0][0]
    assert "Сухо, по делу" in system_prompt
    assert "Только цифры" in system_prompt

    # Settings в БД остались дефолтными.
    settings_resp = await client.get(
        "/api/v1/ai/settings", headers=_auth(token)
    )
    assert settings_resp.json()["tone"] == "good_friend"
    assert settings_resp.json()["complexity_level"] == "family_doctor"


# ---------------------------------------------------------------------------- #
# 9. Прикреплённый профиль попадает в system prompt
# ---------------------------------------------------------------------------- #
async def test_attached_profile_lands_in_system_prompt(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_ai_provider: FakeAIProvider,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    # Создаём профиль.
    await client.post(
        "/api/v1/profile",
        json={
            "first_name": "Алиса",
            "last_name": "Иванова",
            "middle_name": None,
            "birth_date": "1990-05-19",
            "gender": "female",
            "blood_type": None,
            "height_cm": None,
            "weight_kg": None,
            "emergency_contact": None,
            "insurance_info": None,
            "city": None,
            "timezone": "Europe/Moscow",
        },
        headers=_auth(token),
    )

    conv_id = await _create_conversation(client, token)
    resp = await client.post(
        f"/api/v1/ai/conversations/{conv_id}/messages",
        json={
            "message": "Что мне есть на завтрак?",
            "attached_data": {"include_profile": True, "analysis_ids": []},
        },
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert len(fake_ai_provider.calls) == 1
    system_prompt = fake_ai_provider.calls[0][0]
    assert "Алиса" in system_prompt
    assert "Иванова" in system_prompt
    # В ответе сохранены id данных, прикреплённых пользователем.
    attached = resp.json()["user_message"]["attached_data"]
    assert attached is not None
    assert attached["include_profile"] is True


# ---------------------------------------------------------------------------- #
# 10. При timeout от провайдера — 503 с понятным сообщением
# ---------------------------------------------------------------------------- #
async def test_provider_timeout_returns_503(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_ai_provider: FakeAIProvider,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    conv_id = await _create_conversation(client, token)

    fake_ai_provider.side_effect = AIServiceUnavailableError("timeout")
    resp = await client.post(
        f"/api/v1/ai/conversations/{conv_id}/messages",
        json={"message": "Привет"},
        headers=_auth(token),
    )
    assert resp.status_code == 503, resp.text
    assert "ИИ-помощник" in resp.json()["detail"]


# ---------------------------------------------------------------------------- #
# 11. Список бесед сортируется по updated_at DESC
# ---------------------------------------------------------------------------- #
async def test_conversations_listed_newest_first(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    first = await _create_conversation(client, token)
    second = await _create_conversation(client, token)
    resp = await client.get("/api/v1/ai/conversations", headers=_auth(token))
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    # Самая свежая беседа — первая в списке.
    assert ids[0] == second
    assert first in ids


# ---------------------------------------------------------------------------- #
# 12. Архивная беседа исчезает из дефолтного списка
# ---------------------------------------------------------------------------- #
async def test_archive_hides_conversation(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    conv_id = await _create_conversation(client, token)
    archive = await client.post(
        f"/api/v1/ai/conversations/{conv_id}/archive", headers=_auth(token)
    )
    assert archive.status_code == 204
    listed = await client.get("/api/v1/ai/conversations", headers=_auth(token))
    assert all(c["id"] != conv_id for c in listed.json())
    listed_all = await client.get(
        "/api/v1/ai/conversations?include_archived=true", headers=_auth(token)
    )
    assert any(c["id"] == conv_id for c in listed_all.json())


# ---------------------------------------------------------------------------- #
# 13. GET сообщения после safety-события маркированы
# ---------------------------------------------------------------------------- #
async def test_safety_event_persisted_on_get_messages(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    fake_ai_provider: FakeAIProvider,
) -> None:
    _, token = await _register_and_login(client, db_session_factory)
    conv_id = await _create_conversation(client, token)

    await client.post(
        f"/api/v1/ai/conversations/{conv_id}/messages",
        json={"message": "хочу умереть"},
        headers=_auth(token),
    )
    msgs = await client.get(
        f"/api/v1/ai/conversations/{conv_id}/messages", headers=_auth(token)
    )
    assert msgs.status_code == 200
    safety_msgs = [
        m for m in msgs.json() if m["safety_event_type"] == "suicide_risk"
    ]
    assert len(safety_msgs) == 1
    # И провайдер не вызывался для всего флоу.
    assert fake_ai_provider.calls == []
