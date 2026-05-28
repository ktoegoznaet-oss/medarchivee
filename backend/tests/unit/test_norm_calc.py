"""Unit tests for value parsing and abnormality calculation."""

from __future__ import annotations

import pytest

from app.models.analysis import AbnormalType
from app.utils.analysis_norm_calc import (
    ValueParseError,
    calculate_abnormal,
    parse_number,
)


# ---------- parse_number --------------------------------------------------- #


def test_parse_number_handles_comma_decimal() -> None:
    assert parse_number("5,9") == 5.9


def test_parse_number_strips_less_than_prefix() -> None:
    assert parse_number("<2.5") == 2.5


def test_parse_number_strips_greater_than_prefix() -> None:
    assert parse_number(">100") == 100.0


def test_parse_number_rejects_text() -> None:
    with pytest.raises(ValueParseError):
        parse_number("положительный")


def test_parse_number_rejects_empty() -> None:
    with pytest.raises(ValueParseError):
        parse_number("")


# ---------- calculate_abnormal -------------------------------------------- #


def test_calculate_abnormal_normal_value_within_range() -> None:
    is_ab, kind = calculate_abnormal("140", "130", "170")
    assert is_ab is False
    assert kind == AbnormalType.NORMAL


def test_calculate_abnormal_low_value() -> None:
    is_ab, kind = calculate_abnormal("100", "130", "170")
    assert is_ab is True
    assert kind == AbnormalType.LOW


def test_calculate_abnormal_high_value() -> None:
    is_ab, kind = calculate_abnormal("200", "130", "170")
    assert is_ab is True
    assert kind == AbnormalType.HIGH


def test_calculate_abnormal_unknown_for_text_value() -> None:
    is_ab, kind = calculate_abnormal("положительный", "0", "5")
    assert is_ab is False
    assert kind == AbnormalType.UNKNOWN


def test_calculate_abnormal_unknown_when_no_reference() -> None:
    is_ab, kind = calculate_abnormal("12", None, None)
    assert is_ab is False
    assert kind == AbnormalType.UNKNOWN


def test_calculate_abnormal_only_upper_bound() -> None:
    is_ab, kind = calculate_abnormal("3", None, "5")
    assert is_ab is False
    assert kind == AbnormalType.NORMAL
    is_ab, kind = calculate_abnormal("9", None, "5")
    assert is_ab is True
    assert kind == AbnormalType.HIGH
