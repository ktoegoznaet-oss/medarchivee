"""RecoveryService — BIP39 мнемоника как второй путь к DEK.

Архитектура (см. docs/ENCRYPTION.md):

  BIP39 phrase (12 слов = 128 бит энтропии)
        │
        ▼  mnemonic.to_seed(phrase) → PBKDF2-HMAC-SHA512(2048 iter)
        │
       seed (64 байта)
        │
        ▼  первые 32 байта = recovery KEK
        │
        ▼  AES-256-GCM
        │
   recovery_master_key (в users.recovery_master_key)

При reset-password: фраза → recovery KEK → расшифровка DEK → новый KEK
из нового пароля → перешифровка encrypted_dek. Данные пользователя
НЕ перешифровываются — они шифруются под DEK, который не изменился.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from enum import Enum

import structlog
from mnemonic import Mnemonic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account_wipe import AccountWipeCode
from app.models.user import User
from app.services.encryption_service import EncryptionError, EncryptionService

log = structlog.get_logger(__name__)

_WIPE_CODE_TTL = timedelta(minutes=30)
_PHRASE_WORDS = 12  # 128-битная энтропия — стандарт BIP39
_KEY_BYTES = 32


class RecoveryLanguage(str, Enum):
    RUSSIAN = "russian"
    ENGLISH = "english"


class RecoveryError(Exception):
    """Базовый класс recovery-ошибок."""


class PhraseAlreadySetError(RecoveryError):
    """Попытка confirm-phrase, когда recovery_master_key уже заполнен.
    Для смены фразы есть отдельный flow regenerate-phrase."""


class PhraseValidationError(RecoveryError):
    """Фраза не соответствует BIP39 (неверная контрольная сумма,
    неизвестные слова, неверная длина)."""


class PhraseConfirmationFailedError(RecoveryError):
    """Подтверждение через 3 случайных слова не прошло."""


class WipeCodeInvalidError(RecoveryError):
    """Код подтверждения удаления аккаунта неверный/истёк/использован."""


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _generate_wipe_code() -> str:
    # 8-значный numeric — компромисс читаемости и энтропии (~26 бит,
    # достаточно при rate-limit на 5 попыток/15мин и 30-мин TTL).
    return f"{secrets.randbelow(10**8):08d}"


def _phrase_to_kek(phrase: str, lang: RecoveryLanguage) -> bytes:
    """Через стандартный BIP39 seed (64 байта) → берём первые 32."""
    mnemonic = Mnemonic(lang.value)
    if not mnemonic.check(phrase):
        raise PhraseValidationError(f"phrase not valid for lang {lang.value}")
    seed = mnemonic.to_seed(phrase, passphrase="")
    return seed[:_KEY_BYTES]


def _normalize_phrase(raw: str) -> str:
    """Lowercase + объединяем пробелы. BIP39 не использует regex/punctuation."""
    return " ".join(raw.lower().split())


class RecoveryService:
    def __init__(self, db: AsyncSession, encryption: EncryptionService):
        self._db = db
        self._encryption = encryption

    # ---- Generation & confirmation --------------------------------------- #

    def generate_phrase(self, lang: RecoveryLanguage) -> str:
        """Сгенерировать 12-словную BIP39 фразу. НЕ сохраняем в БД —
        пользователь должен явно подтвердить через confirm_phrase().

        Это намеренно: между generate и confirm пользователь должен
        записать фразу и доказать что сохранил (3 случайных слова).
        """
        mnemonic = Mnemonic(lang.value)
        return mnemonic.generate(strength=128)  # 12 слов

    @staticmethod
    def pick_confirmation_indices() -> list[int]:
        """Три случайных индекса (0-based) для подтверждения сохранения фразы."""
        return sorted(secrets.SystemRandom().sample(range(_PHRASE_WORDS), 3))

    async def confirm_phrase(
        self,
        *,
        user: User,
        phrase: str,
        lang: RecoveryLanguage,
        dek: bytes,
        confirmation_indices: list[int],
        confirmation_words: list[str],
    ) -> None:
        """Зашифровать DEK мнемонической фразой и сохранить в users.

        Параметр `dek` — расшифрованный DEK текущей сессии (берётся
        из Redis_keys на уровне API-роутера). Сервис не лезет в Redis
        сам, чтобы можно было его юнит-тестить.
        """
        if user.recovery_phrase_set and user.recovery_master_key is not None:
            raise PhraseAlreadySetError()

        normalized = _normalize_phrase(phrase)
        words = normalized.split()
        if len(words) != _PHRASE_WORDS:
            raise PhraseValidationError("phrase must have 12 words")

        if len(confirmation_indices) != len(confirmation_words) or not confirmation_words:
            raise PhraseConfirmationFailedError()
        for idx, expected in zip(confirmation_indices, confirmation_words, strict=False):
            if not 0 <= idx < _PHRASE_WORDS:
                raise PhraseConfirmationFailedError()
            if words[idx].lower() != expected.lower().strip():
                raise PhraseConfirmationFailedError()

        if len(dek) != _KEY_BYTES:
            raise EncryptionError(f"DEK must be {_KEY_BYTES} bytes, got {len(dek)}")

        recovery_kek = _phrase_to_kek(normalized, lang)
        encrypted_dek_b64 = await self._encryption.encrypt_with_key(
            dek.hex(), recovery_kek
        )

        user.recovery_master_key = encrypted_dek_b64.encode("ascii")
        user.recovery_phrase_set = True
        user.recovery_phrase_lang = lang.value
        await self._db.commit()
        await self._db.refresh(user)
        log.info("recovery.phrase_set", user_id=user.id, lang=lang.value)

    async def regenerate_phrase(self, *, user: User) -> str:
        """Сгенерировать новую фразу для существующего пользователя.

        Использует язык из user.recovery_phrase_lang. Старый
        recovery_master_key обнуляется до тех пор, пока пользователь не
        подтвердит новую фразу через confirm_phrase(). До confirm —
        восстановления через фразу временно нет.
        """
        lang = RecoveryLanguage(user.recovery_phrase_lang or "russian")
        phrase = self.generate_phrase(lang)
        user.recovery_master_key = None
        user.recovery_phrase_set = False
        await self._db.commit()
        await self._db.refresh(user)
        log.info("recovery.phrase_regenerated", user_id=user.id, lang=lang.value)
        return phrase

    # ---- Reset password via phrase --------------------------------------- #

    async def reset_password(
        self,
        *,
        email: str,
        phrase: str,
        new_password: str,
    ) -> User:
        """Расшифровать DEK через фразу, выдать новый KEK из нового пароля,
        перешифровать encrypted_dek. encryption_salt сохраняется."""
        result = await self._db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        # Anti-enumeration: всегда возвращаем ту же ошибку, даже если
        # пользователь не найден или у него нет recovery_phrase. Тогда
        # атакующий не различит «email не зарегистрирован» и «фраза неверна».
        if user is None or user.recovery_master_key is None:
            raise PhraseValidationError()

        lang = RecoveryLanguage(user.recovery_phrase_lang or "russian")
        normalized = _normalize_phrase(phrase)
        try:
            recovery_kek = _phrase_to_kek(normalized, lang)
        except PhraseValidationError:
            raise
        try:
            dek_hex = await self._encryption.decrypt_with_key(
                user.recovery_master_key.decode("ascii"), recovery_kek
            )
        except EncryptionError as exc:
            # Tag mismatch — фраза неверная (или recovery_master_key повреждён).
            log.warning("recovery.reset_failed", user_id=user.id, error=str(exc))
            raise PhraseValidationError() from exc
        dek = bytes.fromhex(dek_hex)

        # Перешифровка encrypted_dek новым KEK из нового пароля.
        new_kek = await self._encryption.derive_user_key(
            new_password, user.encryption_salt
        )
        new_encrypted_dek_b64 = await self._encryption.encrypt_with_key(
            dek.hex(), new_kek
        )

        from app.utils.passwords import hash_password

        user.password_hash = hash_password(new_password)
        user.encrypted_dek = new_encrypted_dek_b64.encode("ascii")
        await self._db.commit()
        await self._db.refresh(user)
        log.info("recovery.password_reset", user_id=user.id)
        return user

    # ---- Wipe account (no phrase, no password) --------------------------- #

    async def request_wipe(self, email: str) -> tuple[User, str] | None:
        """Создаёт wipe-код. Возвращает (user, code) или None, если email не найден.

        Caller (API-роутер) сам решает: отправлять letter и возвращать 200
        одинаково для существующего и несуществующего email (anti-enumeration).
        """
        result = await self._db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            return None
        code = _generate_wipe_code()
        wipe_code = AccountWipeCode(
            user_id=user.id,
            code=code,
            expires_at=_now() + _WIPE_CODE_TTL,
            used=False,
        )
        self._db.add(wipe_code)
        await self._db.commit()
        log.info("recovery.wipe_requested", user_id=user.id)
        return user, code

    async def confirm_wipe(self, *, email: str, code: str) -> User:
        result = await self._db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            raise WipeCodeInvalidError()

        codes_result = await self._db.execute(
            select(AccountWipeCode)
            .where(
                AccountWipeCode.user_id == user.id,
                AccountWipeCode.code == code,
                AccountWipeCode.used.is_(False),
            )
            .order_by(AccountWipeCode.id.desc())
        )
        wipe = codes_result.scalars().first()
        if wipe is None or wipe.expires_at < _now():
            raise WipeCodeInvalidError()

        # CASCADE FK снесут все связанные таблицы (профиль, анализы, AI,
        # инвайты использованные этим юзером и т.п.).
        wipe.used = True
        await self._db.delete(user)
        await self._db.commit()
        log.info("recovery.account_wiped", user_id=user.id)
        return user
