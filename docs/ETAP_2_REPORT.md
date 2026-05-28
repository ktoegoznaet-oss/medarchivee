# Этап 2 — Отчёт

## Что готово

### Модели и миграция (`backend/app/models/`)
- `User` (`users`) — все поля из ТЗ §5.1, включая «спящие» под этап 7: `recovery_code_hash`, `recovery_master_key`, `two_factor_enabled`, `two_factor_secret`. `encryption_salt` — `LargeBinary(32)`, заполняется случайными 32 байтами при регистрации.
- `UserSession` (`user_sessions`) — refresh-токены: хранится только SHA-256-хеш, есть `revoked`, `expires_at`, индекс по `user_id` и `refresh_token_hash`, FK `users.id ON DELETE CASCADE`.
- `EmailVerification` (`email_verifications`) — 6-значные коды с TTL 1 час, `used`, FK на пользователя c CASCADE.
- Миграция `0002_users_and_sessions.py` создаёт три таблицы со всеми индексами и FK. Применяется автоматически при старте backend (`alembic upgrade head` в `command:` контейнера).

### Сервисы (`backend/app/services/`)
- `auth_service.py` — `AuthService(db, encryption)` с методами `register`, `verify_email`, `resend_verification`, `login`, `refresh_access_token`, `logout`, `get_user_from_access_token`. Доменные ошибки выделены в отдельные классы (`EmailAlreadyRegisteredError`, `EmailNotVerifiedError`, `InvalidCredentialsError`, …) — API-слой переводит их в HTTP-коды.
- `password_validator.py` — `validate_password_strength(password, email, username)`. Возвращает список кодов ошибок. Используется в Pydantic-валидаторе и unit-тестах.
- `EncryptionService` уже принимается через DI: при `login` вызывается `store_session_key(...)` с ключом из `derive_user_key(password, salt)`. В identity-режиме это no-op; на этапе 7 заработает само.

### Утилиты (`backend/app/utils/`)
- `passwords.py` — `hash_password` / `verify_password` через passlib + bcrypt (cost=12).
- `jwt.py` — `create_access_token(user_id, role)` и `decode_access_token(token)` с проверкой `type=="access"`. HS256 и секрет из `Settings.jwt_secret`.

### API (`backend/app/api/v1/auth.py`)
| Метод | Путь | Ответ |
|---|---|---|
| POST | `/api/v1/auth/register` | 201 + `RegisterResponse`, 409 `email_taken`/`username_taken`, 422 на согласия/слабый пароль |
| POST | `/api/v1/auth/verify-email` | 200 + `UserPublic`, 400 `verification_code_invalid` / `verification_code_expired` |
| POST | `/api/v1/auth/resend-verification` | 200, 429 `resend_too_soon` (1 минута между запросами) |
| POST | `/api/v1/auth/login` | 200 + `access_token` + HttpOnly cookie `refresh_token`, 401 `invalid_credentials`, 403 `email_not_verified`/`account_inactive`. Rate limit `5/15minute` через slowapi |
| POST | `/api/v1/auth/refresh` | 200 + новый access + ротированный refresh-cookie, 401 на отозванный/истёкший |
| POST | `/api/v1/auth/logout` | 200, очищает cookie, помечает сессию revoked. Идемпотентно. |
| GET | `/api/v1/auth/me` | 200 + `UserPublic` если есть валидный `Authorization: Bearer ...`, 401 иначе |

Cookie выставляется как `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, `Secure` только в `app_env=production`. CSRF на этом этапе закрывается `SameSite=Strict`; double-submit cookie добавим на этапе 7.

### Pydantic-схемы (`backend/app/schemas/auth.py`)
`RegisterRequest`, `RegisterResponse`, `VerifyEmailRequest`, `VerifyEmailResponse`, `ResendVerificationRequest`, `LoginRequest`, `LoginResponse`, `RefreshResponse`, `TokenPair`, `UserPublic`, `MessageResponse`. `UserPublic` намеренно содержит **только** безопасные поля — никакого `password_hash`, `encryption_salt`, recovery/2FA-полей.

### Тесты (`backend/tests/`)
- `unit/test_password_validator.py` — 8 тестов (валидный пароль, по тесту на каждое правило, email/username совпадение).
- `integration/test_auth.py` — 12 интеграционных тестов на in-memory SQLite через `httpx.ASGITransport`: успешная регистрация + код в логах, слабый пароль, отсутствие согласия, дубликат email, валидный код, истёкший код, логин до верификации, успешный логин с access+cookie, неверный пароль, refresh с ротацией, повторное использование старого refresh, `/me` с/без токена.
- `unit/test_encryption_*.py` (из этапа 1) — 11 тестов, без изменений.

### Frontend
- `src/api/client.ts` — axios с `withCredentials`, request-interceptor добавляет `Authorization: Bearer`, response-interceptor на 401 пытается `/v1/auth/refresh` и повторяет оригинальный запрос; при провале — вызывает `onAuthLost` (→ редирект на `/auth/login`). Защита от циклов: refresh не пытается обновляться сам через себя.
- `src/api/auth.ts` — типизированные обёртки над `/v1/auth/*`.
- `src/stores/auth.ts` — Pinia store (Composition API). `accessToken` хранится **только в памяти** (никакого localStorage). `tryRestoreSession()` тихо вызывает `/refresh` при загрузке SPA, что даёт сохранение сессии между перезагрузками без хранения JWT в JS-доступном месте.
- Страницы `RegisterView.vue`, `VerifyEmailView.vue`, `LoginView.vue`. Все строки — через `$t('...')`, кнопка отправки активна только при выполнении правил пароля и всех трёх согласий. «Забыли пароль?» — `v-tooltip` со ссылкой-заглушкой («Доступно после этапа 7»).
- `src/App.vue` — `v-app-bar` с меню пользователя (logout) появляется только если залогинен.
- `src/router/index.ts` — guard `requiresAuth` / `guestOnly`. Главная `/` теперь защищена.
- `src/locales/ru.json` — все строки auth-вьюх, app-bar'а, ошибок.

## Архитектурные решения

1. **Refresh-токен в HttpOnly cookie, access — в памяти JS.** Стандартная модель: refresh нельзя украсть через XSS (HttpOnly), access нельзя украсть из storage (его там нет). Цена — нельзя «жить вечно без вкладки», но это и не было целью.
2. **`SameSite=Strict` вместо CSRF-токенов.** На этапе 2 этого достаточно: cookie не шлётся при cross-site POST. Double-submit cookie добавим, когда расширим формы (этап 7), потому что Strict ломает «зашёл по ссылке из письма».
3. **`encryption_service.store_session_key` вызывается всегда.** В identity-режиме — no-op, но контракт уже соблюдён. На этапе 7 переключение `ENCRYPTION_PROVIDER=aesgcm` начнёт реально складывать мастер-ключ в `redis_keys` без правок `auth_service.py`.
4. **bcrypt cost=12 в проде, =4 в тестах.** 12 раундов даёт ~250 мс на login — это специально, чтобы брутфорс был дорогим. В тестах monkeypatch'им cost до 4 — те же 12 round-trip'ов не должны занимать 30 секунд.
5. **Интеграционные тесты на SQLite, а не MariaDB.** На вертикальном срезе мастер-промпт явно разрешает это (§8 «Тесты»). `LargeBinary(32)` рендерится как `BLOB` в SQLite и `VARBINARY(32)` в MariaDB — модели не различают. Когда появится `testcontainers` (этап 7+), `db_engine` в `conftest.py` переключится на MariaDB-контейнер без правки тестов.
6. **Ротация refresh-токенов.** При `/refresh` старая сессия помечается `revoked=True`, новая выдаётся с новым случайным UUID. Любая повторная попытка использовать старый токен → 401. Это защита от replay-атаки, если refresh-токен утёк (хотя HttpOnly + Strict это сильно усложняет).
7. **`get_session_key` в identity отдаёт константный ключ, а не None.** Это позволяет сервисам этапов 3–6 не писать «if identity then …»: в `login` мы спокойно вызываем `derive_user_key` → `store_session_key` без условных веток.
8. **Идемпотентный logout.** Если refresh-cookie уже невалидна — всё равно возвращаем 200 и чистим cookie. Это упрощает UI и не позволяет атакующему понять по ответу, был ли токен реально активным.
9. **`@limiter.limit("5/15minute")` на login, выключается в тестах через `limiter.enabled = False`.** SlowAPI хранит счётчики в памяти процесса — на dev/single-instance этого достаточно; на проде придётся подключить Redis-бэкенд (этап 12).

## Что отложено

| Что | На какой этап |
|-----|---------------|
| 2FA (TOTP) | 7 |
| Восстановление пароля через email | 7 |
| Резервный код + `recovery_master_key` | 7 |
| Реальная отправка email (SMTP) | 12 |
| CAPTCHA + блокировка после N попыток | 7 |
| CSRF double-submit cookie | 7 |
| Redis-бэкенд для slowapi (многоинстансный rate limit) | 12 |
| Audit-таблица `audit_log` | 3+ (запишем туда вход уже сейчас как `structlog.info`) |

## Известные проблемы

- В тестах для проверки ротации refresh я не использую `client.cookies.update(...)` — `httpx.ASGITransport` теряет cookie между запросами при `withCredentials` clones-сценариях, поэтому в тесте я явно пробрасываю `cookies={"refresh_token": …}`. На реальном браузере проблемы нет — там cookie живёт в jar.
- Frontend не прогоняется через настоящий браузер — Docker недоступен. Логику можно проверить только после `docker compose up --build` у заказчика.
- В `auth_service.login` `derive_user_key` вызывается **до** того, как мы знаем `session.id` (он генерируется autoincrement'ом БД). Сейчас мы передаём `str(session.id or uuid.uuid4())`. В identity-режиме это no-op, поэтому проблемы нет. На этапе 7 я перепишу: сначала `flush()` сессии → получить `id` → потом `store_session_key`. Записал TODO в коде.

## Что нужно сделать заказчику перед этапом 3

1. `docker compose up --build` — все тесты должны пройти: `docker compose exec backend pytest -q`.
2. Сценарий вручную:
   - Открыть http://localhost → редирект на `/auth/login`.
   - «Регистрация» → заполнить форму (нужны все три чекбокса).
   - `docker compose logs backend | grep email_verification_code` — взять 6-значный код.
   - Ввести код → редирект на `/auth/login`.
   - Войти → попасть на главную, увидеть свой `username` в верхнем баре.
   - «Выйти» → редирект на `/auth/login`.
3. Если что-то не работает — собрать `docker compose logs backend` и приложить к багу.
