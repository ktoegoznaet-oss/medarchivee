"""Numeric parsing + abnormality classification for analysis values.

Russian lab forms use comma as decimal separator; semi-quantitative values
(`"<2.5"`, `">100"`) collapse to the threshold; non-numeric values (e.g.
`"положительный"`) yield `UNKNOWN`.
"""

from __future__ import annotations

from app.models.analysis import AbnormalType


class ValueParseError(ValueError):
    """Raised when a textual value cannot be coerced to a number."""


def parse_number(value: str) -> float:
    """Best-effort float parse of typical lab notations.

    Examples:
        "5,9"      → 5.9
        "<2.5"     → 2.5
        ">100"     → 100.0
        " 12,3 "   → 12.3
        "положит." → raises ValueParseError
    """
    if value is None:
        raise ValueParseError("empty")
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        raise ValueParseError("empty")
    if cleaned[0] in ("<", ">", "≤", "≥"):
        cleaned = cleaned[1:].strip()
    try:
        return float(cleaned)
    except ValueError as exc:
        raise ValueParseError(value) from exc


def calculate_abnormal(
    value_str: str,
    reference_min_str: str | None,
    reference_max_str: str | None,
) -> tuple[bool, AbnormalType]:
    """Classify a single value against optional reference bounds.

    Returns `(is_abnormal, abnormal_type)`. `UNKNOWN` means we either could
    not parse the value or have no reference range.
    """
    try:
        value = parse_number(value_str)
    except ValueParseError:
        return False, AbnormalType.UNKNOWN

    has_min = reference_min_str not in (None, "")
    has_max = reference_max_str not in (None, "")
    if not has_min and not has_max:
        return False, AbnormalType.UNKNOWN

    if has_min:
        try:
            ref_min = parse_number(reference_min_str)  # type: ignore[arg-type]
        except ValueParseError:
            return False, AbnormalType.UNKNOWN
        if value < ref_min:
            return True, AbnormalType.LOW

    if has_max:
        try:
            ref_max = parse_number(reference_max_str)  # type: ignore[arg-type]
        except ValueParseError:
            return False, AbnormalType.UNKNOWN
        if value > ref_max:
            return True, AbnormalType.HIGH

    return False, AbnormalType.NORMAL
