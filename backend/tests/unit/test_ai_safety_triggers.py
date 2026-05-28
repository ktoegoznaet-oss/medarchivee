"""Unit tests for AI safety trigger detection."""

from __future__ import annotations

import pytest

from app.services.ai_safety.triggers import (
    check_medical_emergency,
    check_suicide_risk,
)


@pytest.mark.parametrize(
    "text",
    [
        "я хочу умереть",
        "Не хочу больше жить.",
        "иногда думаю покончить с собой",
        "Я думаю о суициде",
        "лучше бы меня не было",
        "это моё последнее сообщение, прощайте",
        "я приняла снотворное",
        "режу вены, помоги",
    ],
)
def test_suicide_risk_true_positives(text: str) -> None:
    assert check_suicide_risk(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Расскажи мне про умеренные физические нагрузки",
        "Хочу узнать, как улучшить сон",
        "Болит голова второй день",
        "У меня снижено настроение, что делать",
        "",
    ],
)
def test_suicide_risk_true_negatives(text: str) -> None:
    assert check_suicide_risk(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "У меня сильная боль в груди и не могу дышать",
        "У отца перекосило лицо и пропала речь",
        "Бабушка приняла много таблеток",
        "Температура 41 уже два часа",
        "Сильное кровотечение из носа, не останавливается",
        "Кажется, у меня судороги, помоги",
        "Дочь отравилась бытовой химией",
        "Похоже на анафилактический шок",
    ],
)
def test_medical_emergency_true_positives(text: str) -> None:
    assert check_medical_emergency(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Иногда побаливает грудь после кофе",
        "Слабо тянет спина по утрам",
        "Какие препараты помогают при насморке",
        "Расскажи про норму гемоглобина",
        "",
    ],
)
def test_medical_emergency_true_negatives(text: str) -> None:
    assert check_medical_emergency(text) is False


def test_suicide_check_is_case_insensitive() -> None:
    assert check_suicide_risk("ХОЧУ УМЕРЕТЬ") is True


def test_emergency_check_handles_extra_whitespace() -> None:
    assert check_medical_emergency("боль  в   груди") is True
