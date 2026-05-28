# Этап 6 — Telegram-бот (базовая версия)

> Дата: 2026-05-20
> Ветка: `master`
> Тип: завершение вертикального среза. Базовая интеграция с Telegram, привязка
> через 6-значный код, тестовая отправка, отдельный сервис в Docker.

---

## 1. Что готово

### Backend

| Модуль | Файлы | Что покрывает (ТЗ v1.1) |
|---|---|---|
| Модели | [backend/app/models/telegram.py](../backend/app/models/telegram.py) | §5/§9.2 — `telegram_bindings`, `telegram_binding_codes` |
| Миграция | [backend/migrations/versions/20260520_0006_telegram_bindings.py](../backend/migrations/versions/20260520_0006_telegram_bindings.py) | Две таблицы + уникальные индексы по `user_id` и `telegram_user_id` |
| Pydantic-схемы | [backend/app/schemas/telegram.py](../backend/app/schemas/telegram.py) | `TelegramBindingStatus`, `TelegramBindingCodeResponse`, `TelegramNotificationSettingsUpdate` |
| Sender | [backend/app/services/telegram_sender.py](../backend/app/services/telegram_sender.py) | Тонкая `httpx`-обёртка над `sendMessage`, возвращает bool — не пробрасывает исключения наружу. |
| Сервис | [backend/app/services/telegram_service.py](../backend/app/services/telegram_service.py) | Генерация кода (TTL 10 мин, инвалидация старых, антиспам 3/мин), привязка по коду с нормализацией `@username`, отвязка с удалением кодов, обновление настроек уведомлений, тестовое сообщение. |
| API | [backend/app/api/v1/telegram.py](../backend/app/api/v1/telegram.py) | `GET /binding`, `POST /binding/code` (`@limiter.limit("3/minute")`), `DELETE /binding`, `PATCH /binding/notifications`, `POST /binding/test` |
| DI | [backend/app/dependencies.py](../backend/app/dependencies.py) | `get_telegram_sender` (`lru_cache` + reset), `get_telegram_service` |
| Конфиг | [backend/app/config.py](../backend/app/config.py) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` |
| Роутер | [backend/app/api/v1/\_\_init\_\_.py](../backend/app/api/v1/__init__.py) | Подключён `telegram.router` |
| ENV-пример | [.env.example](../.env.example) | Блок `TELEGRAM_*` с инструкцией про @BotFather |

### Telegram-бот (отдельный сервис)

| Модуль | Файлы | Назначение |
|---|---|---|
| Entrypoint | [telegram_bot/bot.py](../telegram_bot/bot.py) | aiogram 3.x, long-polling, JSON-логи через `structlog` |
| Конфиг | [telegram_bot/config.py](../telegram_bot/config.py) | Свой `Settings` (mirror подмножества backend), без импорта из backend-пакета |
| Модели | [telegram_bot/db/models.py](../telegram_bot/db/models.py) | Копия `User`, `TelegramBinding`, `TelegramBindingCode` (подсказка §6.2) |
| Session | [telegram_bot/db/session.py](../telegram_bot/db/session.py) | Один async-engine, фабрика сессий |
| Binding DAL | [telegram_bot/db/binding.py](../telegram_bot/db/binding.py) | `find_binding`, `try_bind`, `unbind` — повторяет логику backend-сервиса |
| Handlers | [telegram_bot/handlers/](../telegram_bot/handlers/) | `/start` (с deep-link), `/help`, `/status`, `/today` (заглушка), `/unbind` (inline-подтверждение) |
| Тексты | [telegram_bot/handlers/texts.py](../telegram_bot/handlers/texts.py) | Все user-facing строки в одном месте, легко тестировать |
| Rate-limit | [telegram_bot/handlers/rate_limit.py](../telegram_bot/handlers/rate_limit.py) | Sliding-window limiter в памяти процесса: 5 попыток `/start КОД` в минуту |
| Dockerfile | [telegram_bot/Dockerfile](../telegram_bot/Dockerfile) | python:3.11-slim, deps из requirements.txt |
| Тесты | [telegram_bot/tests/test_handlers.py](../telegram_bot/tests/test_handlers.py) | Тексты + полный binding-flow (валидный/expired/garbage/повторно/unbind) |

### Frontend

| Модуль | Файлы | Назначение |
|---|---|---|
| API-клиент | [frontend/src/api/telegram.ts](../frontend/src/api/telegram.ts) | Типы + методы getBinding/generateCode/unbind/updateNotifications/sendTest |
| Pinia store | [frontend/src/stores/telegram.ts](../frontend/src/stores/telegram.ts) | `binding`, `bindingCode`, методы fetch/generate/unbind/updateSettings/sendTest |
| View | [frontend/src/views/settings/TelegramView.vue](../frontend/src/views/settings/TelegramView.vue) | Дисклеймер + два режима (привязан/нет); таймер кода с countdown; switch-и уведомлений с подписями «активируется на этапе N»; тестовое сообщение; отвязка с подтверждением |
| Меню | [frontend/src/components/AppNavigation.vue](../frontend/src/components/AppNavigation.vue) | Группа «Настройки → Telegram» (готова к расширению) |
| Главная | [frontend/src/views/HomeView.vue](../frontend/src/views/HomeView.vue) | Карточка «Telegram-бот» активирована |
| Роутер | [frontend/src/router/index.ts](../frontend/src/router/index.ts) | `/settings/telegram` (auth+profile) |
| Локализация | [frontend/src/locales/ru.json](../frontend/src/locales/ru.json) | Секция `telegram.*` |

### Docker

| Файл | Изменение |
|---|---|
| [docker-compose.yml](../docker-compose.yml) | Добавлен сервис `telegram_bot` в общую сеть, `depends_on: mariadb (healthy) + backend (started)`, `restart: unless-stopped`, `env_file: .env` |

### Тесты

| Файл | Покрытие |
|---|---|
| [backend/tests/integration/test_telegram.py](../backend/tests/integration/test_telegram.py) | 11 тестов: код 6 цифр + TTL ~10 мин, инвалидация старого, GET unbound, GET bound, PATCH partial update, DELETE + повторный 404, истёкший код, коллизия tg-id, /test через `FakeTelegramSender`, изоляция между пользователями, sender без токена = false. |
| [backend/tests/integration/conftest.py](../backend/tests/integration/conftest.py) | `FakeTelegramSender` фиксирует все вызовы; override `get_telegram_sender` |
| [telegram_bot/tests/test_handlers.py](../telegram_bot/tests/test_handlers.py) | 3 теста на тексты (greeting, help-disclaimer, success-name); 5 тестов на binding flow (valid/expired/garbage/double-use/unbind) |

---

## 2. Архитектурные решения

### 2.1. Отдельный сервис вместо встроенного диспетчера в backend

Бот живёт в собственном Docker-контейнере с собственным `requirements.txt`. Причины:

1. **Изоляция отказов.** Если упадёт aiogram-polling — backend и frontend продолжают работать. Уведомления просто не идут. На этапе 12 добавим healthcheck + автоматический restart.
2. **Зависимости.** aiogram + всё его дерево (aiohttp и т.д.) — несвязные с API. Не тащим лишнее в основной образ.
3. **Деплой.** На проде у бота отдельный жизненный цикл — можно перекатывать без рестарта API.

### 2.2. Копия моделей в боте, а не shared-пакет

Подсказка §6.2 это и предлагала. Сейчас копий немного (3 модели, и из них две — простые); shared-пакет даст больше boilerplate, чем экономии. Если на этапе 10 копий станет 6+, выделим `shared_models` как path-dependency. Это записано в TODO.

### 2.3. Backend — источник истины по схеме

Миграции исполняются **только** из backend-контейнера (`alembic upgrade head` в его CMD). Бот никогда не пишет DDL. Если бы оба сервиса могли менять схему, мы получили бы гонки. Сейчас:
- backend → `alembic upgrade head` → схема обновлена → backend стартует API.
- telegram_bot стартует **позже** (`depends_on: backend: condition: service_started`).

### 2.4. Один валидный код в каждый момент

Когда пользователь нажимает «Получить код» второй раз, мы **помечаем все его предыдущие неиспользованные коды `used=True`** (а не удаляем). Зачем:

- Если у пользователя открыта старая вкладка с старым кодом, попытка использовать его даст «invalid_code» вместо непонятного поведения.
- Аудит-история сохраняется — видно, сколько раз пользователь генерировал коды (диагностика, если жалуется на проблемы с подключением).

### 2.5. Антиспам — на двух уровнях

- **На API** (`POST /binding/code`): `@limiter.limit("3/minute")` по IP + проверка «не более 3 кодов в минуту» на стороне сервиса по user_id. Двойной слой потому, что IP-лимит легко обойти с одного аккаунта через VPN, а user_id-лимит — нет.
- **На боте** (`/start КОД`): in-memory sliding window 5/мин по `telegram_user_id`. На этапе 12 при переходе на webhook + горизонтальное масштабирование — вынесем в Redis.

### 2.6. Нормализация username (без @, нижний регистр)

Хранится `binding.telegram_username = "alice"`, а не `"@AliCE"`. Это:
- избегает дублей при поиске («Alice» vs «alice»);
- упрощает уникальность (если бы понадобилась — сейчас не уникальна, но может пригодиться).

### 2.7. TelegramSender — без исключений

`send_message()` возвращает `bool`. Зачем не raise:
- На этапе 6 единственный сценарий — тестовое сообщение по кнопке. UI отображает либо «Доставлено», либо «Не доставлено», не показывая стектрейс.
- На этапах 9–10 массовая рассылка (Celery): одно упавшее сообщение не должно прерывать пачку — мы хотим вернуть false и пойти дальше.

Все ошибки логируются через `structlog` (`telegram_sender.send_failed`).

### 2.8. Текст тестового сообщения — нейтральный

Согласно подсказке §6.5 и §9.1 ТЗ. Текст: «Тестовое сообщение от МедАрхива. Если вы это видите — связь работает. Сейчас HH:MM UTC.» Никаких имён пользователя, никакой ссылки на медицинское содержание — только метаданные канала.

### 2.9. Дисклеймер виден в трёх местах

1. На странице настроек (баннер `v-alert warning` — самый заметный).
2. В стартовом сообщении бота (для пользователя, который сначала пишет в бота, потом в приложение).
3. В тексте `/help` (для пользователя, который захочет освежить память).

Это не перебор — задача дисклеймера согласно ТЗ важна и требует повторения.

---

## 3. Что НЕ сделано из этапного промпта (и почему)

Ничего из обязательного объёма этапа 6 не отложено. Все пункты §6.1–§6.8 реализованы:
- Модели и миграция — ✅
- Backend service + sender — ✅
- API endpoints с rate-limit — ✅
- Отдельный сервис `telegram_bot` с aiogram 3.x — ✅
- 5 хендлеров + deep-link + inline-подтверждение unbind — ✅
- Frontend view + store + меню + локализация — ✅
- docker-compose service — ✅
- Тесты backend (11) + bot (8) — ✅

Явно отложено по промпту (§«Что отложено» этапа 6):
- Celery beat → этап 10
- Inline-кнопки «Принял/Пропустил» → этап 10
- Уведомления о визитах → этап 9
- Сводка дня с данными → этап 10
- Чат с Иваном Иванычем через Telegram → v1.1
- Webhook вместо long-polling → этап 12

---

## 4. Что нужно заказчику перед запуском

1. Открыть @BotFather в Telegram, выполнить `/newbot`, получить токен.
2. В `.env` положить:
   ```
   TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
   TELEGRAM_BOT_USERNAME=имя_бота_без_@
   ```
3. `docker compose up --build` — стартует 5 сервисов: mariadb, redis, backend, frontend, **telegram_bot**, nginx.
4. Применить миграцию (запустится автоматически при старте backend): создаст `telegram_bindings` и `telegram_binding_codes`.

Без `TELEGRAM_BOT_TOKEN` контейнер `telegram_bot` упадёт со внятным сообщением; backend продолжит работать. Тесты в CI/dev работают без живого токена (mock в conftest).

---

## 5. Ручной сценарий проверки (DoD §1)

1. Залогиниться → меню «Настройки → Telegram».
2. Видеть баннер «⚠️ Содержимое уведомлений проходит через серверы Telegram…».
3. Нажать «Получить код подключения» → увидеть 6 цифр в моноширинном шрифте + таймер «9:54» + кнопку «Открыть бота в Telegram».
4. Открыть deep-link → в Telegram автоматически отправится `/start <код>` → получить приветствие «Привет, <имя>! 👋 Вы успешно подключили МедАрхив к Telegram».
5. Вернуться в приложение → страница автообновится: «Подключено как @<username>» + дата привязки.
6. Нажать «Отправить тестовое сообщение» → в Telegram прийти «Тестовое сообщение от МедАрхива…» → в UI зелёный alert «Тестовое сообщение отправлено».
7. В Telegram отправить `/help` → получить справку с дисклеймером.
8. Отправить `/today` → получить заглушку «На этапе 6 ещё нет данных…».
9. Отправить `/unbind` → нажать inline-кнопку «Да, отвязать» → получить «🔓 Аккаунт отвязан».
10. В приложении — страница вернётся в состояние «не привязан».

---

## 6. Известные проблемы / TODO

- 🟡 `TODO(этап 7)`: при включении AES-GCM поля `telegram_username` останутся незашифрованными — они не помечены 🔒 в ТЗ (это публичная метаданность), но проверить отдельно.
- 🟡 `TODO(этап 10)`: вынести rate-limit бота из памяти процесса в Redis (когда появится Redis-based Celery beat — будет логично туда же).
- 🟡 `TODO(этап 10)`: возможный рефакторинг в `shared_models` — следить за размером дублирования между backend и telegram_bot.
- 🟡 `TODO(этап 12)`: переход с long-polling на webhook (требует HTTPS, публичного домена, и nginx-маршрута `/telegram/webhook/<секрет>`).
- 🟢 На странице настроек по умолчанию открыта только один пункт меню (Telegram); на этапе 7 добавятся «Безопасность» (2FA, recovery code), «Профиль ИИ» — `<v-list-group>` уже подготовлен для расширения.

---

## 7. 🎉 Финал вертикального среза

Этап 6 — последний модуль вертикального среза (этапы 0–6). У пользователя готово:

| Функция | Этап |
|---|---|
| Инфраструктура (docker-compose, MariaDB, Redis, nginx) | 0 |
| Каркас шифрования (identity, AES — заглушка на этап 7) | 1 |
| Регистрация / верификация / логин / refresh / logout | 2 |
| Профиль пациента + хроника, аллергии, семейный анамнез | 3 |
| Анализы + динамика + справочник параметров | 4 |
| Иван Иваныч (чат с Gemini, safety-критический минимум) | 5 |
| Telegram-бот (привязка, тестовая отправка, заглушка `/today`) | **6** |

Перед фазой 2 (этапы 7–12) рекомендую:
1. Пользоваться приложением 2–3 дня в реальном режиме, фиксировать UX-замечания в `docs/UX_FEEDBACK.md`.
2. Проверить, что во всех сервисах 🔒-поля идут только через `EncryptionService` (на этапе 7 включение AES не должно сломать модули).
3. Создать релизный тег: `git tag v0.6.0-vertical-slice-mvp`.
4. Запросить детализацию этапов 7–12 (`09_etapy_7-12_roadmap.md`).

---

## 8. Команда коммита

```
Этап 6: Telegram-бот (базовая версия) — завершение вертикального среза
```
