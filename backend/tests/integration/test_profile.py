"""Integration tests for /api/v1/profile/* and /api/v1/dictionaries/icd10."""

from __future__ import annotations

from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.email_verification import EmailVerification


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


async def _register_login(
    client: AsyncClient,
    session_factory: async_sessionmaker,
    *,
    email: str = "alice@example.com",
    username: str = "alice",
) -> tuple[int, str]:
    """Register + verify email + login. Returns (user_id, access_token)."""
    payload = _valid_register_payload(email=email, username=username)
    register = await client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201, register.text
    user_id = register.json()["user"]["id"]

    async with session_factory() as db:
        code = (
            (
                await db.execute(
                    select(EmailVerification).where(EmailVerification.user_id == user_id)
                )
            )
            .scalars()
            .first()
            .code
        )

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
    assert login.status_code == 200
    return user_id, login.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_VALID_PROFILE: dict[str, object] = {
    "first_name": "Алиса",
    "last_name": "Иванова",
    "middle_name": "Петровна",
    "birth_date": "1990-05-19",
    "gender": "female",
    "blood_type": "O+",
    "height_cm": 165.0,
    "weight_kg": 60.5,
    "emergency_contact": "+7 999 000-00-00",
    "insurance_info": "ОМС: 1234567890",
    "city": "Москва",
    "timezone": "Europe/Moscow",
}


# ---------------------------------------------------------------------------- #
# 1. POST /profile создаёт
# ---------------------------------------------------------------------------- #
async def test_create_profile_returns_201_and_persists(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    resp = await client.post(
        "/api/v1/profile", json=_VALID_PROFILE, headers=_auth(token)
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["first_name"] == "Алиса"
    assert body["gender"] == "female"
    assert body["height_cm"] == 165.0


# ---------------------------------------------------------------------------- #
# 2. POST /profile дважды → 409
# ---------------------------------------------------------------------------- #
async def test_create_profile_twice_is_conflict(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    first = await client.post(
        "/api/v1/profile", json=_VALID_PROFILE, headers=_auth(token)
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/profile", json=_VALID_PROFILE, headers=_auth(token)
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "profile_already_exists"


# ---------------------------------------------------------------------------- #
# 3. Невалидная дата рождения → 422
# ---------------------------------------------------------------------------- #
async def test_create_profile_rejects_future_birth_date(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    payload = {**_VALID_PROFILE, "birth_date": "2099-01-01"}
    resp = await client.post("/api/v1/profile", json=payload, headers=_auth(token))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------- #
# 4. GET /profile до создания → 404
# ---------------------------------------------------------------------------- #
async def test_get_profile_before_create_returns_404(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    resp = await client.get("/api/v1/profile", headers=_auth(token))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------- #
# 5. Round-trip через encryption_service
# ---------------------------------------------------------------------------- #
async def test_round_trip_returns_exact_values(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    await client.post("/api/v1/profile", json=_VALID_PROFILE, headers=_auth(token))
    resp = await client.get("/api/v1/profile", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()

    # Все 🔒-поля должны вернуться точно такими же.
    for key in (
        "first_name",
        "last_name",
        "middle_name",
        "birth_date",
        "gender",
        "blood_type",
        "emergency_contact",
        "insurance_info",
        "city",
    ):
        assert body[key] == _VALID_PROFILE[key], key
    assert body["height_cm"] == 165.0
    assert body["weight_kg"] == 60.5
    assert body["timezone"] == "Europe/Moscow"


# ---------------------------------------------------------------------------- #
# 6. PATCH /profile обновляет только переданные поля
# ---------------------------------------------------------------------------- #
async def test_patch_profile_updates_only_supplied_fields(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    await client.post("/api/v1/profile", json=_VALID_PROFILE, headers=_auth(token))
    patch = await client.patch(
        "/api/v1/profile",
        json={"city": "Санкт-Петербург"},
        headers=_auth(token),
    )
    assert patch.status_code == 200
    body = patch.json()
    assert body["city"] == "Санкт-Петербург"
    # Остальные поля без изменений.
    assert body["first_name"] == "Алиса"
    assert body["blood_type"] == "O+"


# ---------------------------------------------------------------------------- #
# 7. POST weight-history обновляет вес в профиле
# ---------------------------------------------------------------------------- #
async def test_add_weight_record_updates_profile_weight(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    await client.post("/api/v1/profile", json=_VALID_PROFILE, headers=_auth(token))
    add = await client.post(
        "/api/v1/profile/weight-history",
        json={"weight_kg": 58.2, "note": "после похода"},
        headers=_auth(token),
    )
    assert add.status_code == 201, add.text
    history = await client.get(
        "/api/v1/profile/weight-history", headers=_auth(token)
    )
    assert len(history.json()) == 1

    profile = await client.get("/api/v1/profile", headers=_auth(token))
    assert profile.json()["weight_kg"] == 58.2


# ---------------------------------------------------------------------------- #
# 8. Изоляция: пользователь A не видит/удаляет данные пользователя B
# ---------------------------------------------------------------------------- #
async def test_user_a_cannot_touch_user_b_chronic(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token_a = await _register_login(client, db_session_factory)
    _, token_b = await _register_login(
        client,
        db_session_factory,
        email="bob@example.com",
        username="bob",
    )

    create_b = await client.post(
        "/api/v1/profile/chronic-conditions",
        json={"name": "Гипертония", "icd10_code": "I10"},
        headers=_auth(token_b),
    )
    assert create_b.status_code == 201
    cond_id = create_b.json()["id"]

    # Пользователь A читает свой пустой список — записи Б там нет.
    list_a = await client.get(
        "/api/v1/profile/chronic-conditions", headers=_auth(token_a)
    )
    assert list_a.json() == []

    # И A не может ни обновить, ни удалить запись B.
    patch_a = await client.patch(
        f"/api/v1/profile/chronic-conditions/{cond_id}",
        json={"is_active": False},
        headers=_auth(token_a),
    )
    assert patch_a.status_code == 404

    delete_a = await client.delete(
        f"/api/v1/profile/chronic-conditions/{cond_id}", headers=_auth(token_a)
    )
    assert delete_a.status_code == 404


# ---------------------------------------------------------------------------- #
# 9. Добавление хронического заболевания работает
# ---------------------------------------------------------------------------- #
async def test_add_chronic_condition_round_trip(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    create = await client.post(
        "/api/v1/profile/chronic-conditions",
        json={
            "name": "Сахарный диабет 2-го типа",
            "icd10_code": "E11",
            "diagnosed_at": date.today().isoformat(),
            "is_active": True,
        },
        headers=_auth(token),
    )
    assert create.status_code == 201

    listed = await client.get(
        "/api/v1/profile/chronic-conditions", headers=_auth(token)
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["icd10_code"] == "E11"


# ---------------------------------------------------------------------------- #
# 10. ICD-10 search возвращает результаты
# ---------------------------------------------------------------------------- #
async def test_icd10_search_finds_codes(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    resp = await client.get(
        "/api/v1/dictionaries/icd10",
        params={"search": "диаб"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    codes = {entry["code"] for entry in body}
    assert "E10" in codes
    assert "E11" in codes

    # Поиск по коду тоже работает.
    by_code = await client.get(
        "/api/v1/dictionaries/icd10",
        params={"search": "J45"},
        headers=_auth(token),
    )
    assert by_code.json()[0]["code"] == "J45"


# ---------------------------------------------------------------------------- #
# 11. Бонус: allergy CRUD
# ---------------------------------------------------------------------------- #
async def test_allergy_create_and_delete(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login(client, db_session_factory)
    create = await client.post(
        "/api/v1/profile/allergies",
        json={"allergen": "Пенициллин", "severity": "severe"},
        headers=_auth(token),
    )
    assert create.status_code == 201
    aid = create.json()["id"]

    listed = await client.get("/api/v1/profile/allergies", headers=_auth(token))
    assert len(listed.json()) == 1

    delete = await client.delete(
        f"/api/v1/profile/allergies/{aid}", headers=_auth(token)
    )
    assert delete.status_code == 204
    final = await client.get("/api/v1/profile/allergies", headers=_auth(token))
    assert final.json() == []
