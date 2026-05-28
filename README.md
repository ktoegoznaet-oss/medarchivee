# МедАрхив

Self-hosted веб-приложение для хранения и анализа персональных медицинских данных.
Развёртывается одной командой через Docker.

> Главная ценность: все медицинские данные шифруются ключом, производным
> от пароля пользователя. Даже администратор сервера не может прочитать
> данные без пароля пользователя.
>
> **Не заменяет врача.** Это архив и помощник, а не диагностический инструмент.

## Текущая фаза

Подготовка к **закрытой бете** (10 тестировщиков) завершена. Реализовано:

**Базовое MVP** (этапы 0–6):
- Регистрация / верификация email / логин с refresh-токенами
- Профиль пациента, анализы с графиками, ИИ-помощник Gemini
- Telegram-бот с привязкой пользователя

**Подготовка к бете** (Спринты 1–3, Шаги A–K):
- Роли user/admin с `INITIAL_ADMIN_EMAIL` бутстрапом
- SMTP-доставка писем через Yandex + ARQ-очередь
- Инвайт-коды (BIP32, 7 дней) + 3 режима регистрации (closed/invite_only/open)
- **AES-256-GCM шифрование** с двухслойной DEK/KEK архитектурой,
  Argon2id KDF, Redis_keys без persistence — админ технически не может
  расшифровать чужие медданные
- BIP39 мнемоническая фраза для recovery + reset-password + wipe-account
- Система support-тикетов с плавающей кнопкой и админ-просмотром
- Полная админ-панель (дашборд, пользователи, инвайты, тикеты, настройки)
- Отдельный Telegram-бот для админа (команды + push-уведомления)
- GlitchTip/Sentry SDK с PII-фильтром для error tracking
- Экспорт данных пользователем + удаление аккаунта (ФЗ-152)

Шифрование включается переменной `ENCRYPTION_PROVIDER=aesgcm` в `.env`
(дефолт в `.env.example`). Identity-режим сохранён для тестов и dev.

## Быстрый старт (локально)

```bash
# 1. Создать .env и заполнить секреты
cp .env.example .env
# или: bash scripts/init-dev.sh — сгенерирует случайные SECRET_KEY/JWT_SECRET

# 2. (опционально) Получить ключи для интеграций:
#    - Gemini API: https://aistudio.google.com/app/apikey
#    - Telegram-бот: @BotFather → /newbot
#    Без них модули ИИ и Telegram не работают, остальное — работает.

# 3. Поднять стек
docker compose up --build

# 4. Открыть в браузере
#    http://localhost           — главная страница
#    http://localhost/docs      — Swagger UI backend
#    http://localhost/api/health — health-check
```

## Сервисы

| Сервис | Порт хоста | Технологии |
|---|---|---|
| `nginx` | 80 | reverse-proxy для frontend + backend |
| `backend` | — | FastAPI 0.115 + SQLAlchemy 2.0 async |
| `frontend` | — | Vue 3 + TypeScript + Vuetify 3 + Vite |
| `telegram_bot` | — | aiogram 3.x, long-polling |
| `mariadb` | — | MariaDB 11 |
| `redis` | — | Redis 7 (кэш + брокер очередей) |

Никакие порты, кроме 80, наружу не выставлены.

## Документация

- [docs/INDEX.md](docs/INDEX.md) — навигатор по документации
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — общая схема сервисов
- [docs/ENCRYPTION.md](docs/ENCRYPTION.md) — стратегия шифрования
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — инструкция для разработчика
- [docs/ETAP_*_REPORT.md](docs/) — отчёты по этапам 0–6
- [DIAGNOSTIC_REPORT.md](DIAGNOSTIC_REPORT.md) — последний полный аудит кода

## Стек

Backend — FastAPI + SQLAlchemy 2.0 (async) + MariaDB + Redis + Alembic.
Frontend — Vue 3 + TypeScript (strict) + Vuetify 3 + Pinia + vue-i18n.
Telegram-бот — aiogram 3.x + asyncmy.
Инфраструктура — Docker Compose + Nginx.
