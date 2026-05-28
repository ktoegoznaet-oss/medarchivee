# Этап 0 — Отчёт

## Что готово

### Корень репозитория
- `README.md`, `.gitignore`, `.env.example` — заполнены минимально достаточно для этапа 0.
- `docker-compose.yml` с четырьмя сервисами + nginx: `mariadb` (с healthcheck), `redis` (с persistence + healthcheck), `backend` (FastAPI), `frontend` (Vite dev-server), `nginx` (reverse proxy).
- Backend ждёт MariaDB и Redis через `condition: service_healthy` — стартует только когда они готовы.

### Backend (`backend/`)
- `Dockerfile` multi-stage (`builder` → `dev` / `runtime`). На этапе 0 в compose используется target `dev` с `uvicorn --reload`.
- `pyproject.toml` через PEP 621. Зависимости минимальны: FastAPI, SQLAlchemy 2.0 + asyncmy, Alembic, Pydantic v2 + pydantic-settings, structlog, redis (async). Dev: ruff, pytest, pytest-asyncio, httpx, aiosqlite.
- `app/config.py` — типизированный `Settings` через `pydantic-settings`, читает `.env`. Включает `database_url` и `redis_url` как computed property.
- `app/logging_config.py` — структурированные JSON-логи в проде, читаемый текст в dev.
- `app/database.py` — async-движок SQLAlchemy + dependency `get_db()`.
- `app/api/v1/health.py` — `GET /api/health` с реальной проверкой БД (`SELECT 1`) и Redis (`PING`). Возвращает `status`, `version`, `db`, `redis`.
- `app/main.py` — фабрика приложения, CORS на `localhost`/`localhost:5173`, structlog `startup` event.
- `app/models/base.py` — пустой `DeclarativeBase`.
- Alembic настроен на async (`migrations/env.py`), есть baseline-миграция `0001_initial` с пустыми `upgrade()`/`downgrade()`.
- `tests/test_health.py` + `tests/conftest.py` — health-эндпоинт тестируется через `httpx.AsyncClient` + ASGI-transport, БД/Redis замокированы (CI не требует MariaDB).

### Frontend (`frontend/`)
- Vite + Vue 3 + TypeScript (strict).
- Установлены: Vuetify 3, Pinia, Vue Router 4, vue-i18n, Axios, Chart.js + vue-chartjs, dayjs, `@mdi/font`.
- `src/main.ts` — bootstrap (Vuetify + Pinia + Router + i18n).
- `src/router/index.ts` — один route `/` → `Welcome.vue`.
- `src/views/Welcome.vue` — карточка «МедАрхив. Этап 0», подтягивает `/api/health` через axios-клиент.
- `src/locales/ru.json` — все строки страницы вынесены под `welcome.*`.
- `src/api/client.ts` — axios-инстанс с `baseURL = VITE_API_BASE_URL`.
- `eslint.config.js` (flat config), `tsconfig.json` со `strict: true` и алиасом `@/* → src/*`.
- `Dockerfile` multi-stage (`deps` → `dev` / `build` / `prod`). В compose — target `dev`, который поднимает Vite на `0.0.0.0:5173` с polling watch (стабильнее под Docker).

### Nginx
- `nginx/nginx.conf` — базовый конфиг.
- `nginx/conf.d/medarchive.conf` — проксирует `/api/*` и `/docs` на backend, всё остальное (включая WebSocket HMR) — на frontend. Добавлены базовые security-заголовки (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`). HSTS/CSP/SSL — на этапе 12.

### CI / GitHub Actions
`.github/workflows/ci.yml`, 4 job'а:
- `backend-lint` — `ruff check`.
- `backend-test` — `pytest -q` (health-тест на ASGI, без БД).
- `frontend-lint` — `npm run lint`.
- `frontend-build` — `npm run build` (включает `vue-tsc --noEmit`).

### Документация
- `docs/ARCHITECTURE.md` — общая ASCII-схема + слои backend + изоляция данных.
- `docs/DEVELOPMENT.md` — пошаговая инструкция для разработчика.
- `docs/ETAP_0_REPORT.md` (этот файл).

## Архитектурные решения

1. **asyncmy вместо aiomysql.** asyncmy быстрее и активнее поддерживается. Совместим с SQLAlchemy 2.0 + Alembic async. Не требует pure-Python пути и нативно работает на CPython 3.11/3.12. Если возникнет проблема — переключение на aiomysql сводится к одной строке в `pyproject.toml` и `config.database_url`.
2. **MariaDB ждёт health через `healthcheck.sh --connect --innodb_initialized`.** Это рекомендуемый официальным образом healthcheck — он гарантирует, что InnoDB полностью инициализирована, а не только сокет открыт.
3. **Один Redis на этапе 0.** Второй `redis_keys` без persistence добавляется только на этапе 7. Сейчас Redis используется лишь health-эндпоинтом, чтобы убедиться, что подключение работает.
4. **Тесты health не зависят от MariaDB.** В `conftest.py` `get_db` подменяется на стаб, а `_check_redis` — на async-функцию, возвращающую `True`. Это даёт быстрый CI без поднимания контейнеров. Интеграционные тесты на реальной MariaDB появятся, когда появятся модели (этап 1+).
5. **Multi-stage Dockerfile.** Уже сейчас разделены `builder` / `dev` / `runtime` (backend) и `deps` / `dev` / `build` / `prod` (frontend) — чтобы переход в продакшен на этапе 12 не требовал переписывания Dockerfile.
6. **Hot-reload через bind-mount.** В compose `./backend:/app` и `./frontend:/app` — изменения кода применяются без пересборки образа. Для frontend важно: `node_modules` лежит в **отдельном анонимном volume** (`frontend_node_modules`), чтобы хостовая папка `node_modules` (если появится) не перекрывала контейнерную.
7. **Alembic применяется автоматически.** В `command:` backend перед `uvicorn` запускается `alembic upgrade head` — `docker compose up` сразу даёт работоспособное состояние схемы.

## Что отложено и куда

| Что | На какой этап |
|-----|----------------|
| Celery + Celery beat | этап 6 |
| Telegram-бот | этап 6 |
| `redis_keys` (без persistence) | этап 7 |
| Реальный AES-256-GCM (`AESGCMEncryptionService`) | этап 7 |
| 2FA, recovery_master_key логика | этап 7 |
| OCR (pytesseract, pdf2image, OpenCV) | этап 8 |
| Production-конфиг nginx + Let's Encrypt / certbot | этап 12 |
| Установочный скрипт `scripts/install.sh` | этап 12 |
| HSTS / CSP / X-XSS-Protection | этап 12 |

## Известные проблемы

- `package-lock.json` для frontend не создан (он генерируется при первом `npm install` внутри контейнера). CI использует `npm install` вместо `npm ci`, поэтому работает; но при желании более стабильных билдов имеет смысл коммитить lock-файл — это произойдёт автоматически при первом запуске у заказчика.
- `pyproject.toml` без точной фиксации patch-версий (`>=X.Y`) — для воспроизводимости в проде на этапе 12 имеет смысл сгенерировать `requirements.lock` через `pip-compile`.
- Healthcheck-тест в pytest проверяет happy-path. Тест на degraded-состояние (когда БД/Redis недоступны) добавим, когда появятся отдельные модули `services/health/`.

## Что нужно сделать заказчику перед этапом 1

1. Проверить, что `docker compose up --build` запускается без ошибок на машине заказчика.
2. Открыть в браузере http://localhost — должна появиться карточка «МедАрхив. Этап 0».
3. Открыть http://localhost/api/health — должен вернуться JSON со `status: ok`, `db: ok`, `redis: ok`.
4. Создать GitHub-репозиторий и сделать первый push (`git add . && git commit -m "Этап 0: инфраструктура и скелет репозитория"`).
5. Скопировать `.env.example` в `.env` (если ещё не сделано). Реальные значения SECRET_KEY/JWT_SECRET на этапе 0 неважны, но к этапу 7 будут заменены на криптостойкие случайные.
