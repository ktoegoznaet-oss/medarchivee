"""Integration tests for /api/v1/analyses/* and the parameter dictionary."""

from __future__ import annotations

from datetime import date, timedelta

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


def _profile_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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
    }
    base.update(overrides)
    return base


async def _register_login_with_profile(
    client: AsyncClient,
    factory: async_sessionmaker,
    *,
    email: str = "alice@example.com",
    username: str = "alice",
    profile_overrides: dict[str, object] | None = None,
) -> tuple[int, str]:
    payload = _valid_register_payload(email=email, username=username)
    register = await client.post("/api/v1/auth/register", json=payload)
    assert register.status_code == 201
    user_id = register.json()["user"]["id"]

    async with factory() as db:
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
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile_data = _profile_payload(**(profile_overrides or {}))
    profile = await client.post("/api/v1/profile", json=profile_data, headers=headers)
    assert profile.status_code == 201, profile.text
    return user_id, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------- #
# 1. Создание записи с 3 значениями — abnormal расставлен
# ---------------------------------------------------------------------------- #
async def test_create_record_calculates_abnormal_for_each_value(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)

    body = {
        "analysis_date": "2026-05-10",
        "lab_name": "Инвитро",
        "doctor_referral": "Терапевт",
        "notes": "Плановый ОАК",
        "values": [
            {
                "parameter_code": "hemoglobin",
                "parameter_name": "Гемоглобин",
                "value": "135",
                "unit": "г/л",
                "reference_min": "120",
                "reference_max": "150",
            },
            {
                "parameter_code": "cholesterol_total",
                "parameter_name": "Общий холестерин",
                "value": "6,4",
                "unit": "ммоль/л",
                "reference_min": "3.1",
                "reference_max": "5.2",
            },
            {
                "parameter_code": "tsh",
                "parameter_name": "ТТГ",
                "value": "0,2",
                "unit": "мМЕ/л",
                "reference_min": "0.4",
                "reference_max": "4.0",
            },
        ],
    }
    resp = await client.post("/api/v1/analyses", json=body, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    full = resp.json()
    assert full["lab_name"] == "Инвитро"
    by_code = {v["parameter_code"]: v for v in full["values"]}
    assert by_code["hemoglobin"]["abnormal_type"] == "normal"
    assert by_code["cholesterol_total"]["abnormal_type"] == "high"
    assert by_code["tsh"]["abnormal_type"] == "low"


# ---------------------------------------------------------------------------- #
# 2. Авто-нормы из справочника
# ---------------------------------------------------------------------------- #
async def test_create_record_auto_fills_norms_from_dictionary(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    body = {
        "analysis_date": "2026-05-10",
        "values": [
            {
                "parameter_code": "hemoglobin",
                "parameter_name": "Гемоглобин",
                "value": "100",
                "unit": "г/л",
            }
        ],
    }
    resp = await client.post("/api/v1/analyses", json=body, headers=_auth(token))
    assert resp.status_code == 201
    value = resp.json()["values"][0]
    # Для женщины 35 лет норма 120–150 → 100 это LOW.
    assert value["reference_min"] == "120.0"
    assert value["reference_max"] == "150.0"
    assert value["abnormal_type"] == "low"
    assert value["is_abnormal"] is True


# ---------------------------------------------------------------------------- #
# 3. Текстовое значение → UNKNOWN
# ---------------------------------------------------------------------------- #
async def test_text_value_is_unknown(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    body = {
        "analysis_date": "2026-05-10",
        "values": [
            {
                "parameter_code": "urine_glucose",
                "parameter_name": "Глюкоза в моче",
                "value": "отрицательный",
                "unit": "качеств.",
            }
        ],
    }
    resp = await client.post("/api/v1/analyses", json=body, headers=_auth(token))
    assert resp.status_code == 201
    value = resp.json()["values"][0]
    assert value["abnormal_type"] == "unknown"
    assert value["is_abnormal"] is False


# ---------------------------------------------------------------------------- #
# 4. Численное значение выше нормы → HIGH
# ---------------------------------------------------------------------------- #
async def test_explicit_high_value(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    body = {
        "analysis_date": "2026-05-10",
        "values": [
            {
                "parameter_name": "Креатинин",
                "value": "200",
                "unit": "мкмоль/л",
                "reference_min": "53",
                "reference_max": "97",
            }
        ],
    }
    resp = await client.post("/api/v1/analyses", json=body, headers=_auth(token))
    value = resp.json()["values"][0]
    assert value["abnormal_type"] == "high"


# ---------------------------------------------------------------------------- #
# 5. GET / без фильтров возвращает все записи
# ---------------------------------------------------------------------------- #
async def test_list_returns_all_records(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    for day in ("2026-04-01", "2026-05-01"):
        body = {
            "analysis_date": day,
            "values": [
                {
                    "parameter_code": "hemoglobin",
                    "parameter_name": "Гемоглобин",
                    "value": "135",
                    "unit": "г/л",
                    "reference_min": "120",
                    "reference_max": "150",
                }
            ],
        }
        await client.post("/api/v1/analyses", json=body, headers=_auth(token))

    listed = await client.get("/api/v1/analyses", headers=_auth(token))
    assert listed.status_code == 200
    data = listed.json()
    assert len(data) == 2
    # Сортировка по дате DESC.
    assert data[0]["analysis_date"] >= data[1]["analysis_date"]


# ---------------------------------------------------------------------------- #
# 6. ?only_abnormal=true фильтрует
# ---------------------------------------------------------------------------- #
async def test_list_only_abnormal_filter(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    # Запись в норме
    await client.post(
        "/api/v1/analyses",
        json={
            "analysis_date": "2026-04-01",
            "values": [
                {
                    "parameter_code": "hemoglobin",
                    "parameter_name": "Гемоглобин",
                    "value": "135",
                    "unit": "г/л",
                    "reference_min": "120",
                    "reference_max": "150",
                }
            ],
        },
        headers=_auth(token),
    )
    # Запись с отклонением
    await client.post(
        "/api/v1/analyses",
        json={
            "analysis_date": "2026-05-01",
            "values": [
                {
                    "parameter_code": "hemoglobin",
                    "parameter_name": "Гемоглобин",
                    "value": "90",
                    "unit": "г/л",
                    "reference_min": "120",
                    "reference_max": "150",
                }
            ],
        },
        headers=_auth(token),
    )

    listed = await client.get(
        "/api/v1/analyses?only_abnormal=true", headers=_auth(token)
    )
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["abnormal_count"] == 1


# ---------------------------------------------------------------------------- #
# 7. Изоляция: GET чужой записи → 404
# ---------------------------------------------------------------------------- #
async def test_other_user_cannot_read_record(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token_a = await _register_login_with_profile(client, db_session_factory)
    create = await client.post(
        "/api/v1/analyses",
        json={
            "analysis_date": "2026-05-01",
            "values": [
                {
                    "parameter_code": "hemoglobin",
                    "parameter_name": "Гемоглобин",
                    "value": "135",
                    "unit": "г/л",
                }
            ],
        },
        headers=_auth(token_a),
    )
    record_id = create.json()["id"]

    _, token_b = await _register_login_with_profile(
        client, db_session_factory, email="bob@example.com", username="bob"
    )
    resp = await client.get(
        f"/api/v1/analyses/{record_id}", headers=_auth(token_b)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------- #
# 8. История параметра отсортирована по дате
# ---------------------------------------------------------------------------- #
async def test_parameter_history_sorted_by_date(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    for day, val in (("2026-03-01", "130"), ("2026-04-01", "138"), ("2026-05-01", "135")):
        await client.post(
            "/api/v1/analyses",
            json={
                "analysis_date": day,
                "values": [
                    {
                        "parameter_code": "hemoglobin",
                        "parameter_name": "Гемоглобин",
                        "value": val,
                        "unit": "г/л",
                        "reference_min": "120",
                        "reference_max": "150",
                    }
                ],
            },
            headers=_auth(token),
        )

    history = await client.get(
        "/api/v1/analyses/parameters/hemoglobin/history", headers=_auth(token)
    )
    assert history.status_code == 200
    body = history.json()
    dates = [p["analysis_date"] for p in body["points"]]
    assert dates == sorted(dates)
    assert body["parameter_name"] == "Гемоглобин"


# ---------------------------------------------------------------------------- #
# 9. PATCH значения пересчитывает is_abnormal
# ---------------------------------------------------------------------------- #
async def test_patch_value_recomputes_abnormal(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    create = await client.post(
        "/api/v1/analyses",
        json={
            "analysis_date": "2026-05-01",
            "values": [
                {
                    "parameter_code": "hemoglobin",
                    "parameter_name": "Гемоглобин",
                    "value": "135",
                    "unit": "г/л",
                    "reference_min": "120",
                    "reference_max": "150",
                }
            ],
        },
        headers=_auth(token),
    )
    value_id = create.json()["values"][0]["id"]

    patch = await client.patch(
        f"/api/v1/analyses/values/{value_id}",
        json={"value": "100"},
        headers=_auth(token),
    )
    assert patch.status_code == 200
    assert patch.json()["abnormal_type"] == "low"
    assert patch.json()["is_abnormal"] is True


# ---------------------------------------------------------------------------- #
# 10. DELETE удаляет cascade
# ---------------------------------------------------------------------------- #
async def test_delete_record_cascades(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    create = await client.post(
        "/api/v1/analyses",
        json={
            "analysis_date": "2026-05-01",
            "values": [
                {
                    "parameter_code": "hemoglobin",
                    "parameter_name": "Гемоглобин",
                    "value": "135",
                    "unit": "г/л",
                }
            ],
        },
        headers=_auth(token),
    )
    rid = create.json()["id"]

    delete = await client.delete(
        f"/api/v1/analyses/{rid}", headers=_auth(token)
    )
    assert delete.status_code == 204
    listed = await client.get("/api/v1/analyses", headers=_auth(token))
    assert listed.json() == []


# ---------------------------------------------------------------------------- #
# 11. Поиск справочника по синониму
# ---------------------------------------------------------------------------- #
async def test_dictionary_search_by_synonym(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    resp = await client.get(
        "/api/v1/dictionaries/analysis-parameters?search=HGB",
        headers=_auth(token),
    )
    codes = {p["code"] for p in resp.json()}
    assert "hemoglobin" in codes


# ---------------------------------------------------------------------------- #
# 12. Параметр-detail с гендером возвращает женскую норму
# ---------------------------------------------------------------------------- #
async def test_parameter_detail_returns_gender_specific_norm(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    resp = await client.get(
        "/api/v1/dictionaries/analysis-parameters/hemoglobin?gender=female&age=35",
        headers=_auth(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["applicable_norm"]["min"] == 120
    assert body["applicable_norm"]["max"] == 150
    assert body["applicable_norm"]["gender"] == "female"


# ---------------------------------------------------------------------------- #
# Bonus: date range filter works
# ---------------------------------------------------------------------------- #
async def test_list_filters_by_date_range(
    client: AsyncClient, db_session_factory: async_sessionmaker
) -> None:
    _, token = await _register_login_with_profile(client, db_session_factory)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    last_year = (date.today() - timedelta(days=400)).isoformat()
    for day in (last_year, yesterday):
        await client.post(
            "/api/v1/analyses",
            json={
                "analysis_date": day,
                "values": [
                    {
                        "parameter_code": "hemoglobin",
                        "parameter_name": "Гемоглобин",
                        "value": "135",
                        "unit": "г/л",
                    }
                ],
            },
            headers=_auth(token),
        )

    recent = await client.get(
        "/api/v1/analyses",
        params={"date_from": (date.today() - timedelta(days=30)).isoformat()},
        headers=_auth(token),
    )
    assert len(recent.json()) == 1
