# Руководство разработчика

## Требования

- Docker 24+ с плагином Compose v2 (`docker compose ...`)
- Git
- Опционально: Python 3.11 и Node 20 для запуска тестов/линтеров **вне** контейнеров

## Первый запуск

```bash
# 1. Клонировать репозиторий
git clone <repo-url> medarchive
cd medarchive

# 2. Скопировать переменные окружения
cp .env.example .env       # на Windows PowerShell: Copy-Item .env.example .env

# 3. Поднять стек
docker compose up --build
```

После старта:

| URL | Что открывается |
|-----|------------------|
| http://localhost | Приветственная страница (Vue) |
| http://localhost/docs | Swagger UI backend |
| http://localhost/api/health | JSON health-check |

## Полезные команды

```bash
# Логи backend (живой tail)
docker compose logs -f backend

# Прогон тестов
docker compose exec backend pytest

# Линтер backend
docker compose exec backend ruff check app tests

# Применить миграции вручную (на старте backend это делается автоматически)
docker compose exec backend alembic upgrade head

# Создать новую миграцию
docker compose exec backend alembic revision -m "описание"

# Тесты frontend (на этапе 0 заготовка)
docker compose exec frontend npm run test

# Сборка фронта в продакшен-режиме
docker compose exec frontend npm run build
```

## Жизненный цикл этапа

1. Подать в Claude Code мастер-промпт (`01_master_prompt.md`)
2. Подать этапный промпт (`02_etap_N_*.md`)
3. После завершения этапа — прочитать `docs/ETAP_N_REPORT.md`
4. Закоммитить: `Этап N: <короткое описание>`

## Соглашения

- Все строки UI — через `$t('key')` в `frontend/src/locales/ru.json`.
- Все секреты — только в `.env`, никогда в коде.
- Любой отложенный TODO — с пометкой `# TODO(этап N):` или `// TODO(этап N):`.
- Никаких `print()` для отладки — `structlog.get_logger(__name__)`.
