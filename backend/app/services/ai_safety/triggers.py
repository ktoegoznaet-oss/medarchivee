"""Trigger detection for the two stage-5 safety scenarios.

Подход — простой regex: на этапе 5 этого достаточно, чтобы не пропустить
очевидные случаи. На этапе 12 эту функцию заменит полный safety-каркас
(вкл. семантику + ИИ-классификатор), а пока — explicit-list по §8.12.2.

False positives для нас приемлемее, чем false negatives: если человек
шутит про «давай покончим с собой» в переносном смысле, он получит
прописанный, заботливый ответ — это не страшно. Пропустить настоящий
случай — недопустимо.
"""

from __future__ import annotations

import re

# ---- Suicide risk (§8.12.2.1) -------------------------------------------- #

_SUICIDE_PATTERNS = [
    r"хочу\s+умереть",
    r"хочется\s+умереть",
    r"не\s+хочу(?:\s+\S+){0,3}\s+жить",
    r"не\s+хочется(?:\s+\S+){0,3}\s+жить",
    r"больше\s+не\s+могу\s+так",
    r"покончить\s+с\s+собой",
    # «самоуб» как префикс ловит «самоубийство», «самоубиться», «самоубью»,
    # «самоубьюсь». Прежний char-class [ийц] терял варианты с «ь».
    r"самоуб",
    r"суицид",
    r"нет\s+смысла\s+жить",
    r"лучше\s+бы\s+меня\s+не\s+было",
    r"лучше\s+бы\s+я\s+умер",
    r"это\s+моё\s+последнее\s+сообщение",
    r"прощай(?:те)?[\s.!]*$",
    r"я\s+(?:приняла?|выпила?)\s+(?:таблетки|снотворн|яд)",
    r"свести\s+счёты\s+с\s+жизнью",
    r"вены\s+(?:режу|порезал|поре[жз])",
    r"режу\s+вены",
    r"режу\s+себе",
]

# ---- Medical emergency (§8.12.2.2) --------------------------------------- #

_MEDICAL_EMERGENCY_PATTERNS = [
    r"боль\s+в\s+груди",
    r"давит\s+в\s+груди",
    r"жмёт\s+в\s+груди",
    r"не\s+могу\s+дышать",
    r"задыхаюсь",
    r"перестал[аи]?\s+дышать",
    r"онеме(?:ла|ло|ние)\s+(?:половин|рук|ног|лиц|сторон)",
    r"потерял[аи]?\s+сознание",
    r"теряю\s+сознание",
    r"обморок",
    r"сильное\s+кровотечение",
    r"кровь\s+(?:фонтаном|не\s+останавливается)",
    r"принял[аи]?\s+много\s+таблеток",
    r"переборщил[аи]?\s+(?:с\s+)?таблетк",
    r"отравил(?:ся|ась|ись)",
    r"температура\s+(?:40|41|42)",
    r"судороги",
    r"анафилак",
    r"инсульт",
    r"инфаркт",
    r"перекосило\s+лицо",
    r"речь\s+пропала",
]


_SUICIDE_RE = re.compile("|".join(_SUICIDE_PATTERNS), flags=re.IGNORECASE)
_EMERGENCY_RE = re.compile("|".join(_MEDICAL_EMERGENCY_PATTERNS), flags=re.IGNORECASE)


def check_suicide_risk(text: str) -> bool:
    """Return True if the message matches one of the suicide-risk patterns."""
    if not text:
        return False
    return _SUICIDE_RE.search(text) is not None


def check_medical_emergency(text: str) -> bool:
    """Return True if the message describes a medical emergency."""
    if not text:
        return False
    return _EMERGENCY_RE.search(text) is not None
