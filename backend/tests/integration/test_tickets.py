"""Integration tests: пользовательские тикеты + админ-доступ.

Шаг G Спринта 2. Использует identity-провайдер (тикеты не шифруются).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import dependencies
from app.config import settings
from app.main import app
from app.models.email_verification import EmailVerification
from app.models.support import SupportTicket, TicketAttachment
from app.services.ticket_service import TicketService


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
    assert reg.status_code == 201
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


@pytest.fixture
def uploads_root(tmp_path: Path) -> Path:
    """Изолированный uploads-каталог для каждого теста."""
    return tmp_path / "uploads"


@pytest.fixture
def use_test_uploads(
    uploads_root: Path,
    db_session_factory: async_sessionmaker,
    fake_admin_notifier,
):
    """Override TicketService на тестовый uploads_root.

    Передаём явно fake_admin_notifier — иначе сервис создаст свой
    NullAdminNotifier, и тесты на уведомления тут не сработают
    (мы используем conftest-fake_admin_notifier для assertions).
    """

    async def _override():
        async with db_session_factory() as session:
            yield TicketService(
                db=session,
                uploads_root=uploads_root,
                admin_notifier=fake_admin_notifier,
            )

    app.dependency_overrides[dependencies.get_ticket_service] = _override
    yield
    app.dependency_overrides.pop(dependencies.get_ticket_service, None)


def _form_data(
    *,
    ticket_type: str = "bug",
    title: str = "Кнопка не работает",
    description: str = "Жму, ничего не происходит.",
) -> dict[str, str]:
    return {
        "payload": json.dumps(
            {
                "type": ticket_type,
                "title": title,
                "description": description,
                "url": "https://test/x",
                "user_agent": "Mozilla/5.0 test",
                "screen_size": "1920x1080",
            }
        )
    }


# ----- User: create + list + get + comment ---------------------------- #


async def test_create_ticket_minimal(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {access}"},
        data=_form_data(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Кнопка не работает"
    assert body["status"] == "new"
    assert body["type"] == "bug"
    assert body["attachments"] == []


async def test_create_ticket_with_screenshot(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    uploads_root: Path,
    use_test_uploads,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    resp = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {access}"},
        data=_form_data(),
        files={"screenshot": ("bug.png", io.BytesIO(fake_png), "image/png")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["attachments"]) == 1
    assert body["attachments"][0]["original_filename"] == "bug.png"
    # Файл должен быть записан на диск под случайным именем.
    ticket_id = body["id"]
    files = list((uploads_root / "tickets" / str(ticket_id)).iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == fake_png
    assert "bug.png" not in files[0].name  # имя случайное


async def test_create_ticket_rejects_too_large_attachment(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    huge = b"x" * (6 * 1024 * 1024)  # 6 МБ
    resp = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {access}"},
        data=_form_data(),
        files={"screenshot": ("huge.png", io.BytesIO(huge), "image/png")},
    )
    assert resp.status_code == 413
    assert resp.json()["detail"] == "attachment_too_large"


async def test_create_ticket_rejects_unknown_mime(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    resp = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {access}"},
        data=_form_data(),
        files={"screenshot": ("a.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 415


async def test_list_my_tickets(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    headers = {"Authorization": f"Bearer {access}"}
    for i in range(3):
        await client.post(
            "/api/v1/tickets",
            headers=headers,
            data=_form_data(title=f"Тикет {i}"),
        )
    resp = await client.get("/api/v1/tickets/mine", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["tickets"]) == 3


async def test_get_ticket_includes_comments_but_not_internal(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Создаём админа + пользователя.
    monkeypatch.setattr(settings, "initial_admin_email", "admin@x.com")
    admin_access = await _register_verify_login(
        client, db_session_factory, "admin@x.com", "admin"
    )
    monkeypatch.setattr(settings, "initial_admin_email", "")
    user_access = await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )

    create = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {user_access}"},
        data=_form_data(),
    )
    ticket_id = create.json()["id"]

    # Админ оставляет публичный и внутренний комменты.
    await client.post(
        f"/api/v1/admin/tickets/{ticket_id}/comments",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"body": "Видно пользователю", "is_internal": False},
    )
    await client.post(
        f"/api/v1/admin/tickets/{ticket_id}/comments",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"body": "СЕКРЕТНАЯ ВНУТРЕННЯЯ ЗАМЕТКА", "is_internal": True},
    )

    user_view = await client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers={"Authorization": f"Bearer {user_access}"},
    )
    assert user_view.status_code == 200
    bodies = [c["body"] for c in user_view.json()["comments"]]
    assert "Видно пользователю" in bodies
    assert "СЕКРЕТНАЯ ВНУТРЕННЯЯ ЗАМЕТКА" not in bodies

    admin_view = await client.get(
        f"/api/v1/admin/tickets/{ticket_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert admin_view.status_code == 200
    bodies = [c["body"] for c in admin_view.json()["comments"]]
    assert "СЕКРЕТНАЯ ВНУТРЕННЯЯ ЗАМЕТКА" in bodies


async def test_other_user_cannot_view_ticket(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    alice_access = await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )
    bob_access = await _register_verify_login(
        client, db_session_factory, "bob@example.com", "bob"
    )
    create = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {alice_access}"},
        data=_form_data(),
    )
    ticket_id = create.json()["id"]

    bob_view = await client.get(
        f"/api/v1/tickets/{ticket_id}",
        headers={"Authorization": f"Bearer {bob_access}"},
    )
    # 404 — anti-IDOR, не раскрываем существование тикета.
    assert bob_view.status_code == 404


async def test_user_can_add_comment(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
) -> None:
    access = await _register_verify_login(client, db_session_factory)
    headers = {"Authorization": f"Bearer {access}"}
    create = await client.post("/api/v1/tickets", headers=headers, data=_form_data())
    ticket_id = create.json()["id"]
    resp = await client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=headers,
        json={"body": "Дополнительная информация"},
    )
    assert resp.status_code == 201
    assert resp.json()["is_internal"] is False  # юзер не может ставить internal


# ----- Admin: list + filter + status change --------------------------- #


async def test_admin_lists_all_tickets(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "admin@x.com")
    admin_access = await _register_verify_login(
        client, db_session_factory, "admin@x.com", "admin"
    )
    monkeypatch.setattr(settings, "initial_admin_email", "")
    user_access = await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )

    for ttype in ("bug", "suggestion", "question"):
        await client.post(
            "/api/v1/tickets",
            headers={"Authorization": f"Bearer {user_access}"},
            data=_form_data(ticket_type=ttype),
        )

    listing = await client.get(
        "/api/v1/admin/tickets",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert listing.status_code == 200
    assert len(listing.json()["tickets"]) == 3
    # У админа должен быть email пользователя.
    assert listing.json()["tickets"][0]["user_email"] == "alice@example.com"

    # Фильтр по типу.
    bugs = await client.get(
        "/api/v1/admin/tickets?type_filter=bug",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert len(bugs.json()["tickets"]) == 1


async def test_admin_changes_status(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "admin@x.com")
    admin_access = await _register_verify_login(
        client, db_session_factory, "admin@x.com", "admin"
    )
    monkeypatch.setattr(settings, "initial_admin_email", "")
    user_access = await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )
    create = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {user_access}"},
        data=_form_data(),
    )
    ticket_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/admin/tickets/{ticket_id}/status",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"status": "resolved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


async def test_non_admin_cannot_access_admin_tickets(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    user_access = await _register_verify_login(client, db_session_factory)
    resp = await client.get(
        "/api/v1/admin/tickets",
        headers={"Authorization": f"Bearer {user_access}"},
    )
    assert resp.status_code == 403


# ----- Attachments isolation ------------------------------------------ #


async def test_other_user_cannot_download_attachment(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "")
    alice_access = await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )
    bob_access = await _register_verify_login(
        client, db_session_factory, "bob@example.com", "bob"
    )

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    create = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {alice_access}"},
        data=_form_data(),
        files={"screenshot": ("a.png", io.BytesIO(fake_png), "image/png")},
    )
    ticket_id = create.json()["id"]

    async with db_session_factory() as db:
        attachment = (await db.execute(select(TicketAttachment))).scalars().first()
        attachment_id = attachment.id

    bob = await client.get(
        f"/api/v1/tickets/{ticket_id}/attachments/{attachment_id}",
        headers={"Authorization": f"Bearer {bob_access}"},
    )
    assert bob.status_code == 404


async def test_admin_can_download_attachment(
    client: AsyncClient,
    db_session_factory: async_sessionmaker,
    use_test_uploads,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "initial_admin_email", "admin@x.com")
    admin_access = await _register_verify_login(
        client, db_session_factory, "admin@x.com", "admin"
    )
    monkeypatch.setattr(settings, "initial_admin_email", "")
    user_access = await _register_verify_login(
        client, db_session_factory, "alice@example.com", "alice"
    )

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    create = await client.post(
        "/api/v1/tickets",
        headers={"Authorization": f"Bearer {user_access}"},
        data=_form_data(),
        files={"screenshot": ("a.png", io.BytesIO(fake_png), "image/png")},
    )
    ticket_id = create.json()["id"]

    async with db_session_factory() as db:
        attachment = (await db.execute(select(TicketAttachment))).scalars().first()
        attachment_id = attachment.id

    resp = await client.get(
        f"/api/v1/tickets/{ticket_id}/attachments/{attachment_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert resp.status_code == 200
    assert resp.content == fake_png
