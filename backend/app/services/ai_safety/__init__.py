"""AI safety: trigger detection + canned responses.

На этапе 5 покрыты два самых критичных сценария:
  * `suicide_risk`        — намерение причинить себе вред / суицидальные
                            высказывания.
  * `medical_emergency`   — симптомы, требующие немедленного вызова 03/112.

Все остальные категории (§8.12.3–§8.12.5: домашнее насилие, дети,
prompt injection, статьи УК) — отложены до этапа 12.
"""

from app.services.ai_safety.responses import (
    MEDICAL_EMERGENCY_RESPONSE_TEMPLATE,
    SUICIDE_RESPONSE_TEMPLATE,
)
from app.services.ai_safety.triggers import (
    check_medical_emergency,
    check_suicide_risk,
)

__all__ = [
    "MEDICAL_EMERGENCY_RESPONSE_TEMPLATE",
    "SUICIDE_RESPONSE_TEMPLATE",
    "check_medical_emergency",
    "check_suicide_risk",
]
