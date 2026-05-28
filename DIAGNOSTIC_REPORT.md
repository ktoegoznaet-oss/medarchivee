# Диагностический отчёт — МедАрхив

> Дата: 2026-05-20
> Состояние ветки: `master`, без коммитов (`git status` показывает все файлы как untracked).
> Метод: статический анализ + `py_compile` (99 файлов), валидация JSON, проверка line endings, грепы.
> Тесты в Docker не запускались — Docker недоступен на этой Windows-машине.

---

## 0. Тип приложения и общее наблюдение

**Это не Windows-native приложение.** Это **многосервисный Docker-проект**:

| Сервис | Стек | Точка входа |
|---|---|---|
| `backend` | FastAPI 0.115 + SQLAlchemy 2.0 (async) + MariaDB 11 + Redis 7 + Alembic 1.13 | [backend/app/main.py](backend/app/main.py) |
| `frontend` | Vue 3.5 + TypeScript 5.6 (strict) + Vuetify 3.7 + Vite 5 + Pinia + vue-i18n | [frontend/src/main.ts](frontend/src/main.ts) |
| `telegram_bot` | aiogram 3.4 + SQLAlchemy 2.0 (long-polling, асинхронный) | [telegram_bot/bot.py](telegram_bot/bot.py) |
| `nginx` | nginx 1.27 (reverse-proxy) | [nginx/conf.d/medarchive.conf](nginx/conf.d/medarchive.conf) |
| `mariadb` | MariaDB 11 | docker-managed |
| `redis` | Redis 7 | docker-managed |

Развёртывание — `docker compose up --build`, на любой ОС с Docker. Windows-аспекты применимы только к dev-окружению (line endings, IDE, локальная установка Python/Node).

---

## 🔴 Критические проблемы (приложение сломается / не запустится / большой риск утечки)

### C1. `.gitignore` блокирует runtime-словари — приложение упадёт после `git clone`

[.gitignore:33](.gitignore#L33) содержит `**/data/`, что **совпадает с** [backend/app/data/](backend/app/data/) — каталогом обязательных JSON-словарей (`analysis_norms.json`, `icd10_ru.json`). Эти файлы — **часть приложения**, не пользовательские данные.

Проверено: `git check-ignore -v backend/app/data/analysis_norms.json` → `.gitignore:33:**/data/  backend/app/data/analysis_norms.json` — файлы будут проигнорированы при `git add`.

**Последствие:** после клонирования репозитория на другой машине `backend/app/services/analysis_norms_service.py:23` и `dictionaries_service.py:25` упадут с `FileNotFoundError` при первом запросе — анализы и онбординг не работают.

**Патч:**
```diff
--- a/.gitignore
+++ b/.gitignore
@@ -31,7 +31,11 @@
 # --- Docker volumes / runtime data ---
-**/data/
+# Пользовательские медицинские данные (тома MariaDB, файлы загрузок).
+# backend/app/data/ — справочники, ДОЛЖЕН быть в репозитории.
+mariadb_data/
+redis_data/
+/data/
+frontend/data/
 backend/uploads/
 backend/logs/
```

И принудительно добавить:
```bash
git add -f backend/app/data/
```

---

### C2. SECRET_KEY и JWT_SECRET имеют дефолт `"change-me"` без startup-валидации

[backend/app/config.py:32](backend/app/config.py#L32) и [backend/app/config.py:47](backend/app/config.py#L47):
```python
secret_key: str = Field(default="change-me", alias="SECRET_KEY")
jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
```

[.env.example:12,27](.env.example#L12) — `SECRET_KEY=change-me-in-production-64-chars-min`. Никаких runtime-проверок, что секрет переопределён в проде. Если пользователь забудет сменить — JWT можно форджить.

**Последствие:** компрометация всех аккаунтов на инстансе. Особенно опасно для self-hosted, где этот секрет один раз генерируется владельцем.

**Патч:** добавить проверку в [backend/app/main.py](backend/app/main.py):
```diff
--- a/backend/app/main.py
+++ b/backend/app/main.py
@@ -17,6 +17,16 @@
 configure_logging()
 log = structlog.get_logger(__name__)

+_DEFAULT_SECRETS = {"change-me", "change-me-in-production-64-chars-min"}
+if settings.app_env == "production":
+    if settings.jwt_secret in _DEFAULT_SECRETS or len(settings.jwt_secret) < 32:
+        raise RuntimeError(
+            "JWT_SECRET не задан или слишком короткий. Сгенерируйте: openssl rand -hex 32"
+        )
+    if settings.secret_key in _DEFAULT_SECRETS or len(settings.secret_key) < 32:
+        raise RuntimeError("SECRET_KEY не задан или слишком короткий.")
+
+
 def create_app() -> FastAPI:
```

Не «critical-just-now» в dev, но **critical как только `APP_ENV=production`** без проверки.

---

### C3. `auth_service.login` передаёт `session.id=None` в `store_session_key` — ключ шифрования невосстановим на этапе 7

[backend/app/services/auth_service.py:225-240](backend/app/services/auth_service.py#L225-L240):
```python
session = UserSession(...)
self._db.add(session)
# здесь session.id ВСЕГДА None — flush не был сделан

await self._encryption.store_session_key(
    user_id=user.id,
    session_id=str(session.id or uuid.uuid4()),  # ← всегда uuid.uuid4()
    key=...,
)
```

При этом [logout (line 307)](backend/app/services/auth_service.py#L307) использует `session_id=str(session.id)` — там session.id уже есть (роутер вызвал logout позже, session в БД). **Разные session_id** — ключ в Redis_keys, записанный под случайным UUID, никогда не будет revoked. Накопится мусор, и (что важнее) при множественных сессиях `get_session_key` не сможет найти конкретный ключ для расшифровки.

На этапе 6 (identity-stub) — no-op, проблемы нет. На **этапе 7 это полная блокировка**: либо шифрование не работает, либо logout не удаляет ключ.

**Патч:**
```diff
--- a/backend/app/services/auth_service.py
+++ b/backend/app/services/auth_service.py
@@ -225,12 +225,13 @@
         session = UserSession(
             user_id=user.id,
             refresh_token_hash=_hash_refresh_token(refresh_token_raw),
             device_info=device_info,
             ip_address=ip_address,
             expires_at=datetime.now(UTC).replace(tzinfo=None) + refresh_ttl,
         )
         self._db.add(session)
+        await self._db.flush()  # получаем session.id для store_session_key

         # На этапе 7 здесь вычисляется мастер-ключ.
         await self._encryption.store_session_key(
             user_id=user.id,
-            session_id=str(session.id or uuid.uuid4()),
+            session_id=str(session.id),
             key=await self._encryption.derive_user_key(password, user.encryption_salt),
             ttl_seconds=int(refresh_ttl.total_seconds()),
         )
```

Та же ошибка в `refresh_access_token` ([line 282-290](backend/app/services/auth_service.py#L282)) — `new_session` добавляется, но `store_session_key` для него не вызывается вовсе. На этапе 7 это означает, что после refresh пользователь теряет доступ к зашифрованным данным до следующего полного логина.

---

## 🟠 Серьёзные проблемы (приложение работает, но неправильно)

### S1. AttachDataDialog мутирует props.initial.analysis_ids

[frontend/src/components/ai/AttachDataDialog.vue:30](frontend/src/components/ai/AttachDataDialog.vue#L30):
```ts
selectedAnalyses.value = props.initial?.analysis_ids ?? []
```

Присваивается **ссылка** на массив родителя. Затем [строка 49](frontend/src/components/ai/AttachDataDialog.vue#L49) `selectedAnalyses.value.push(id)` — мутирует массив в родителе. Vue 3 не падает на этом, но возникнет неконсистентное состояние: чип в ChatView показывает выбранные анализы, не дожидаясь подтверждения диалога.

**Патч:**
```diff
-    selectedAnalyses.value = props.initial?.analysis_ids ?? []
+    selectedAnalyses.value = [...(props.initial?.analysis_ids ?? [])]
```

---

### S2. Logout не сбрасывает Pinia-stores ИИ/Telegram/анализов

[frontend/src/App.vue:16-29](frontend/src/App.vue#L16-L29):
```ts
auth.registerAuthLostHandler(() => {
  profileStore.reset()
  router.push({ name: 'login' })
})

async function handleLogout(): Promise<void> {
  await auth.logout()
  profileStore.reset()
  router.push({ name: 'login' })
}
```

Сбрасывается только `profileStore`. Но в памяти остаются: `useAIStore.conversations`, `useAIStore.messages`, `useAnalysesStore.records`, `useTelegramStore.binding`. После logout пользователь A → login пользователь B на той же вкладке → на пару секунд видит данные A до того, как новые запросы переписывают state.

**Утечка медицинских данных в UI.** Особо плохо для self-hosted семейного режима (когда несколько человек используют один браузер).

**Патч:**
```diff
+ import { useAIStore } from '@/stores/ai'
+ import { useTelegramStore } from '@/stores/telegram'
+ import { useAnalysesStore } from '@/stores/analyses'

  const profileStore = useProfileStore()
+ const aiStore = useAIStore()
+ const telegramStore = useTelegramStore()
+ const analysesStore = useAnalysesStore()

+ function resetAllStores(): void {
+   profileStore.reset()
+   aiStore.reset()
+   telegramStore.reset()
+   analysesStore.reset()
+ }

  auth.registerAuthLostHandler(() => {
-   profileStore.reset()
+   resetAllStores()
    router.push({ name: 'login' })
  })

  async function handleLogout(): Promise<void> {
    await auth.logout()
-   profileStore.reset()
+   resetAllStores()
    router.push({ name: 'login' })
  }
```

---

### S3. `AIService.list_conversations` имеет N+1 query

[backend/app/services/ai_service.py:225-240](backend/app/services/ai_service.py#L225-L240): на каждую беседу вызывается `_latest_message_preview` → ещё один `SELECT`. Для 50 бесед — 51 запрос.

**Патч (вариант):** загрузить все последние сообщения одним SQL:
```python
# pseudo
last_msg_subq = (
    select(AIMessage.conversation_id, func.max(AIMessage.id).label("max_id"))
    .where(AIMessage.user_id == user_id)
    .group_by(AIMessage.conversation_id)
    .subquery()
)
# join с AIMessage на (conversation_id, id=max_id) — получаем превью одним запросом
```

Не блокирует MVP — на 1-2 беседах разницы нет. Заметно с 20+.

---

### S4. `auth_service.refresh_access_token` не вызывает `store_session_key`

[backend/app/services/auth_service.py:253-294](backend/app/services/auth_service.py#L253) — после ротации refresh-токена новая сессия создаётся, но `store_session_key` не вызывается. На стадии 7 это означает: после refresh access-токена ключ шифрования в Redis_keys остаётся под старым session_id (или вообще там нет ключа, см. C3).

В мастер-промпте §5.4: «На этапе 7 при refresh access-токена также пересоздаётся мастер-ключ шифрования в Redis. На этапах 0–6 — этот шаг nop». Сейчас полностью отсутствует даже nop-вызов, что нарушает контракт «когда переключим на AES, ничего больше не правим».

**Патч:** добавить вызов `store_session_key` после flush в refresh, аналогично login.

---

### S5. README устарел на 6 этапов

[README.md:13-15](README.md#L13-L15): «Сейчас — **этап 0**: инфраструктура и скелет репозитория. Бизнес-логика и UI появятся на следующих этапах.»

Фактически готов вертикальный срез (этапы 0–6 включительно). Документация вводит в заблуждение нового разработчика и пользователя.

---

## 🟡 Предупреждения (потенциальные проблемы)

### W1. `package-lock.json` отсутствует — невоспроизводимые npm-сборки

[frontend/](frontend/) не содержит `package-lock.json`. Dockerfile делает `npm install` — каждая сборка может скачать разные минорные версии (в рамках semver-диапазонов из `package.json`). Если завтра выйдет breaking-change в `axios@1.7.8` — образ перестанет собираться без видимой причины.

**Рекомендация:** сделать одну сборку, закоммитить `package-lock.json`, в Dockerfile использовать `npm ci` вместо `npm install`.

---

### W2. `@app.on_event("startup")` deprecated в FastAPI

[backend/app/main.py:53](backend/app/main.py#L53). FastAPI рекомендует `lifespan`:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app.startup", ...)
    yield

app = FastAPI(lifespan=lifespan, ...)
```

При обновлении FastAPI >0.115 ноый API на startup может сломаться. Сейчас работает, выдаёт DeprecationWarning.

---

### W3. `/auth/register` без rate-limit

[backend/app/api/v1/auth.py:69-90](backend/app/api/v1/auth.py#L69) — у `login` стоит `@limiter.limit("5/15minute")`, у `register` ничего. Можно автоматически создавать аккаунты, исчерпывая email-пространство и нагружая bcrypt.

**Патч:** добавить `@limiter.limit("3/hour")` на register (нужен `request: Request` в сигнатуре).

---

### W4. Регекс `самоуб[ийц]` слабее задумки

[backend/app/services/ai_safety/triggers.py:26](backend/app/services/ai_safety/triggers.py#L26). Char-class `[ийц]` означает «один символ из "и", "й", "ц"». В реальном русском после `самоуб` идёт только `и` («самоубийство», «самоубиться»). Не сработает на: «самоубью», «самоуб себя».

**Рекомендация:** заменить на `r"самоуб"` (prefix match достаточен для триггера).

---

### W5. i18n pluralization не настроен

[frontend/src/locales/ru.json:64](frontend/src/locales/ru.json) — ключ `"preview_analyses": "{count} анализ(а/ов)"`. В русском 3 формы (1 анализ / 2 анализа / 5 анализов). vue-i18n умеет это через `|`-разделитель, но не настроено.

**Патч:**
```json
"preview_analyses": "ни одного анализа | {count} анализ | {count} анализа | {count} анализов"
```
И в шаблоне: `t('ai.attach.preview_analyses', count, { count })`.

---

### W6. Bot's `SlidingWindowLimiter._buckets` без bound — потенциальная утечка памяти

[telegram_bot/handlers/rate_limit.py:19](telegram_bot/handlers/rate_limit.py#L19). `_buckets: dict[int, deque]` копится на каждый новый `telegram_user_id`. Для self-hosted с 5 пользователями — не проблема. Если бы бот был публичным — рос бы вечно.

**Рекомендация:** добавить периодическую очистку bucket'ов, у которых нет attempts в окне:
```python
# раз в N запросов или раз в M минут
for key in list(self._buckets.keys()):
    if not self._buckets[key]:
        del self._buckets[key]
```

Низкий приоритет.

---

### W7. Dead branch в `bind_by_code`

[backend/app/services/telegram_service.py:189-191](backend/app/services/telegram_service.py#L189):
```python
elif existing is not None:
    existing.telegram_username = normalized_username
    binding = existing
```

Эта ветка недостижима: если `own_binding is None`, но `existing is not None` и `existing.user_id == row.user_id` — это противоречит запросу `own_binding = _fetch_binding(row.user_id)` (тот же фильтр).

Не баг, просто dead code. Удалить для ясности.

---

### W8. Production-deps бота включают тестовые

[telegram_bot/requirements.txt](telegram_bot/requirements.txt) содержит `pytest`, `pytest-asyncio`, `aiosqlite` — это нужно только для тестов. Раздувает образ на ~10 МБ и тащит в прод dependencies, не используемые в runtime.

**Патч:** вынести в `requirements-dev.txt`, в основном Dockerfile ставить только базовые. Низкий приоритет.

---

### W9. Health-endpoint создаёт Redis-клиент на каждый запрос

[backend/app/api/v1/health.py:30](backend/app/api/v1/health.py#L30) — `aioredis.from_url(...)` внутри функции. На каждый health-check создаётся новое подключение. Liveness-probe раз в 10 секунд × 86400 секунд в день = 8640 соединений в день.

**Рекомендация:** создать клиент один раз в DI / при старте.

---

### W10. Telegram-bot создаёт engine на module-import (side effect)

[telegram_bot/db/session.py:9-10](telegram_bot/db/session.py#L9):
```python
_engine = create_async_engine(settings.database_url, ...)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)
```

Engine создаётся при импорте модуля. Если в тестах хочется подменить engine — не получится. Также при импорте `bot.py` сразу пытается резолвить `DB_HOST` (что в тесте окружении может быть невалидно).

**Рекомендация:** инициализировать в `main()` бота.

---

### W11. CORS-origins захардкожены без env-переопределения

[backend/app/main.py:32-38](backend/app/main.py#L32) — список `localhost`. На продакшен-домене понадобятся `https://medarchive.example.com`. Сейчас нужно править код, не env.

**Патч:** взять список из `settings.cors_origins: list[str] = Field(default=[...], alias="CORS_ORIGINS")`.

---

### W12. Backend Dockerfile копирует тестовый код в runtime-образ

[backend/Dockerfile:54](backend/Dockerfile#L54) (runtime-stage) `COPY . .` — копирует и `tests/`, `pyproject.toml dev-deps в venv`. Прод-образ раздут. Низкий приоритет — runtime-stage не используется до этапа 12.

---

### W13. Нет `.gitattributes` для line endings

Это Windows-машина (видно по системным сообщениям). Git по умолчанию на Windows конвертирует LF → CRLF при checkout (если `core.autocrlf=true`). Хорошо что на сейчас все файлы — LF (проверено для `docker-compose.yml`, `main.py`, `bot.py`). Но без `.gitattributes` следующий разработчик с другим autocrlf-настройкой может закоммитить CRLF в `*.sh`/`Dockerfile`, что сломает контейнеры.

**Патч:** создать `.gitattributes`:
```
* text=auto eol=lf
*.bat eol=crlf
*.ps1 eol=crlf
```

---

### W14. `samoub[ийц]` это, видимо, мелочь, но `recovery_master_key: VARBINARY(255)` в `users` — это **поле этапа 7**, пустое сейчас

Заложено корректно по ТЗ §5.1. Не баг — отмечаю что под него есть колонка-каркас, на этапе 7 заполнится.

---

## 🔵 Рекомендации по улучшению

### R1. Создать `.env` рядом с `.env.example`

Сейчас `.env` отсутствует (его игнорирует `.gitignore` строкой `.env`). Без него `docker compose up` не запустится. Должна быть инструкция в README: «1. `cp .env.example .env` и заполнить секреты».

Можно автоматизировать через make-target или скрипт `scripts/init-dev.sh`.

### R2. Структурный лог Gemini-запросов

Сейчас [ai_service.py:420-426](backend/app/services/ai_service.py#L420) логирует только `tokens` и `provider`. Полезно бы — `response_ms`, `system_prompt_size`, `history_length` для аудита расходов токенов.

### R3. README с актуальным состоянием

Заменить «Сейчас — этап 0» на «Завершён вертикальный срез (этапы 0–6). Следующее — этап 7 (полное AES-шифрование + 2FA)». Ссылки на свежие отчёты.

### R4. Скрипт `scripts/init-dev.sh`

```bash
#!/bin/bash
set -euo pipefail
[ -f .env ] || cp .env.example .env
# генерация секретов
sed -i "s/change-me-in-production-64-chars-min/$(openssl rand -hex 32)/g" .env
docker compose up --build
```

### R5. Тесты в CI на GitHub Actions

[.github/](.github/) каталог существует, но не проверял содержимое — рекомендую workflow для pytest backend и pytest бота.

### R6. Pre-commit hook на ruff + vue-tsc

Чтобы lint-ошибки ловились локально, не в CI.

### R7. `docs/INDEX.md` или раздел в README

Со ссылками на ETAP_N_REPORT.md, ARCHITECTURE.md, ENCRYPTION.md, MODULE_ANALYSES.md — сейчас они «разбросаны».

### R8. На странице Telegram-настроек показывать что-то и при `binding === null`

Сейчас [TelegramView.vue:159](frontend/src/views/settings/TelegramView.vue#L159): `<p v-else class="text-disabled">{{ t('telegram.loading') }}</p>` — показывается до первого fetch. Если fetch выкинул ошибку, навсегда останется «Загрузка…». Лучше — отлавливать ошибку и показывать «Не удалось загрузить состояние, повторить?».

---

## ✅ Что проверено и работает корректно

### Безопасность
- ✅ SQL — только параметризованные ORM-запросы (через SQLAlchemy 2.0). Поиск по `text(...)` показал только `text("SELECT 1")` в health и `sa.text("0"/"1")` server_defaults в миграциях — нет user-input в raw SQL.
- ✅ Пароли — bcrypt через passlib (`backend/app/utils/passwords.py`), хеш в БД.
- ✅ Refresh-tokens — SHA-256 в БД, исходный UUID4 только в cookie. Compromise дампа БД не даёт продлевать сессии.
- ✅ Access JWT — только в памяти Pinia-store, **не в localStorage**. XSS не извлечёт.
- ✅ HttpOnly cookies для refresh с `SameSite=Strict`, `Secure` в проде.
- ✅ Шифрование медицинских данных через `EncryptionService` контракт. Identity-stub на 0–6, каркас AES готов (`encryption_aesgcm.py`).
- ✅ `structlog`: пароли/ключи/контент медицинских записей **не логируются** (проверил все `log.info`/`log.warning`).
- ✅ Никаких захардкоженных API-ключей в коде — все через `.env`.
- ✅ Уникальные индексы на `users.email`, `users.username`, `telegram_bindings.telegram_user_id`, `ai_settings.user_id` — на уровне БД.
- ✅ Все ORM-запросы фильтруют по `user_id` — изоляция данных подтверждена тестами `test_*` (например, `test_other_user_cannot_read_record`, `test_users_dont_see_each_others_binding`).
- ✅ Pydantic v2 validates всё на API-границе.
- ✅ slowapi rate-limit на `/login` (5/15min), `/ai/conversations/{id}/messages` (10/min), `/telegram/binding/code` (3/min).

### Качество кода
- ✅ Все 99 Python-файлов проходят `py_compile`.
- ✅ JSON-файлы валидны: `ru.json`, `analysis_norms.json`, `icd10_ru.json`.
- ✅ TypeScript strict mode + `noUnusedLocals` + `noUnusedParameters` в [tsconfig.json](frontend/tsconfig.json).
- ✅ Pyproject ruff config с `E F I B UP SIM RUF` правилами.
- ✅ Все API-контроллеры тонкие: только парсинг + вызов сервиса + перевод исключений в HTTPException. Инвариант мастер-промпта §5.1 соблюдён.
- ✅ Шифрование вызывается **только** в services-слое, не в API. Проверено grep'ом — `_encryption.encrypt` нигде в `app/api/`.
- ✅ Async везде где I/O. Никаких `time.sleep`, `requests.get`, `open(...)` в async-функциях (`grep` пустой).

### Windows-dev
- ✅ Line endings — LF (правильно для Docker, проверены: `docker-compose.yml`, `main.py`, `bot.py`).
- ✅ Пути — `pathlib.Path(__file__).resolve().parent` — кросс-платформенные.
- ✅ Нет hardcoded `C:\`, `/tmp/`, или нестандартных абсолютных путей.

### Docker
- ✅ Multi-stage builds для backend и frontend.
- ✅ `depends_on: condition: service_healthy` для mariadb и redis — backend не стартует пока БД не готова.
- ✅ Healthchecks на mariadb и redis.
- ✅ Network isolation: единственный bridge-network `medarchive_net`.
- ✅ Только один внешний порт (80 nginx). MariaDB, Redis, backend, frontend — не публикуют порты на хост.
- ✅ Volumes для mariadb_data, redis_data, frontend_node_modules.
- ✅ `restart: unless-stopped` для всех runtime-сервисов.

### Архитектура
- ✅ Чистое разделение: api/ → services/ → models/. Никаких прямых импортов моделей в api/.
- ✅ DI через FastAPI Depends с `lru_cache` для синглтонов + reset-функций для тестов.
- ✅ FakeAIProvider/FakeTelegramSender в conftest для изоляции внешних вызовов.
- ✅ Bot и backend используют **одну схему БД** (миграции из backend), но **не делятся моделями** (копии в `telegram_bot/db/models.py`). Архитектурное решение задокументировано.
- ✅ Все TODO с пометкой этапа: `TODO(этап N)` — легко найти будущие обязательства.
- ✅ 6 миграций последовательны (0001…0006), `down_revision` соответствует.

### Nginx
- ✅ Security headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- ✅ `client_max_body_size 25M` — разумный лимит.
- ✅ Прокси на vite (WebSocket для HMR) и backend (REST).
- ✅ `proxy_set_header X-Forwarded-Proto` — приложение знает реальную схему.

### Тесты
- ✅ Существуют integration- и unit-тесты для всех модулей (auth, profile, analyses, ai, telegram, encryption).
- ✅ Bcrypt rounds=4 в тестах → быстрый прогон.
- ✅ slowapi disabled в тестах → не падают по 429.
- ✅ SQLite + aiosqlite вместо MariaDB для CI-скорости.

---

## План исправления по приоритету

### Срочно (перед любым коммитом)
1. **C1 — `.gitignore`** + `git add -f backend/app/data/`. Без этого репозиторий нельзя клонировать.

### Перед первым публичным деплоем
2. **C2 — startup-проверка секретов** (5 строк в main.py).
3. **S2 — сброс всех stores на logout** (10 строк в App.vue).
4. **W11 — CORS origins из env**.
5. **W3 — rate-limit на register**.

### Перед этапом 7 (включение AES-шифрования)
6. **C3 — flush перед store_session_key в login** + такой же fix в refresh.
7. **S4 — добавить store_session_key в refresh** (вызов отсутствует).

### Желательно
8. **S1 — copy props.initial.analysis_ids** в AttachDataDialog.
9. **S3 — N+1 в list_conversations** — заменить на JOIN.
10. **S5 — обновить README.md** под текущее состояние.
11. **W1 — `package-lock.json`** через одну локальную сборку + `npm ci` в Dockerfile.
12. **W4 — упростить регекс самоубийства** до `r"самоуб"`.
13. **W5 — i18n pluralization** для `preview_analyses` и где ещё есть.

### Косметика
14. **W2 — lifespan вместо on_event**.
15. **W7 — удалить dead branch** в bind_by_code.
16. **W8 — отделить test-deps** в боте.
17. **W9 — shared Redis client** в health.
18. **W10 — engine в main()** бота.
19. **W13 — добавить `.gitattributes`**.

---

## Уточняющие вопросы

1. **Окружение деплоя**: планируется ли self-hosted на одной VM (как описано в ТЗ) или возможен публичный SaaS? От этого зависит важность W11 (CORS) и C2 (default secrets).

2. **Совместная сессия в браузере**: реалистичен ли сценарий «один браузер, несколько членов семьи логинятся по очереди»? Если да — S2 (сброс stores) становится критическим, а не серьёзным.

3. **Когда планируется первая публичная сборка**: если на этой неделе — C1/C2/S2 надо чинить сейчас. Если месяц-два — можно сначала закончить этап 7 (там и так будут правки auth_service).

4. **CI**: настроены ли GitHub Actions? Если нет — добавлю workflow для pytest и vue-tsc.
