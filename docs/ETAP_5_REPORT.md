# Этап 5 — ИИ-помощник «Иван Иваныч» (базовая версия)

> Дата: 2026-05-19
> Ветка: `master`
> Тип: вертикальный срез, базовая интеграция с Gemini, manual data access, safety-критический минимум.

---

## 1. Что готово

### Backend

| Модуль | Файлы | Что покрывает (ТЗ v1.1) |
|---|---|---|
| Модели | [backend/app/models/ai.py](../backend/app/models/ai.py) | §5.12 — `ai_settings`, `ai_conversations`, `ai_messages` |
| Миграция | [backend/migrations/versions/20260519_0005_ai_assistant.py](../backend/migrations/versions/20260519_0005_ai_assistant.py) | Создаёт три таблицы + индексы (`user_id`, `(conversation_id, created_at)`) |
| Pydantic-схемы | [backend/app/schemas/ai.py](../backend/app/schemas/ai.py) | Settings/Conversation/Message DTO, AttachedDataDTO |
| Провайдер-интерфейс | [backend/app/services/ai_providers/base.py](../backend/app/services/ai_providers/base.py) | Абстрактный `AIProvider` с `generate(system_prompt, messages, max_tokens)` |
| Gemini | [backend/app/services/ai_providers/gemini.py](../backend/app/services/ai_providers/gemini.py) | REST-вызов `gemini-1.5-flash:generateContent` через `httpx`. Обработка 429/503/400. Один ретрай на timeout. Парсинг `usageMetadata.totalTokenCount`. |
| Фабрика | [backend/app/services/ai_providers/factory.py](../backend/app/services/ai_providers/factory.py) | Выбор провайдера по `AISettings.preferred_provider` |
| Safety-триггеры | [backend/app/services/ai_safety/triggers.py](../backend/app/services/ai_safety/triggers.py) | Regex по §8.12.2 — 18 паттернов suicide, 22 паттерна emergency |
| Safety-ответы | [backend/app/services/ai_safety/responses.py](../backend/app/services/ai_safety/responses.py) | Канонические тексты с 8-800-2000-122 (психолог) и 103/112 (скорая) |
| Сервис | [backend/app/services/ai_service.py](../backend/app/services/ai_service.py) | CRUD бесед, отправка сообщения, шифрование контента+attached_data, формирование system prompt по тону/сложности/режиму |
| API | [backend/app/api/v1/ai.py](../backend/app/api/v1/ai.py) | `GET/PATCH /ai/settings`, CRUD `/ai/conversations`, `GET /messages`, `POST /messages` (rate limit 10/min/IP), `POST /archive`, `DELETE /conversations/{id}` |
| DI | [backend/app/dependencies.py](../backend/app/dependencies.py) | `get_ai_service`, `get_ai_provider_factory` (с `lru_cache` + reset для тестов) |
| Конфиг | [backend/app/config.py](../backend/app/config.py) | `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-1.5-flash`), `GEMINI_TEMPERATURE` (0.4), `GEMINI_MAX_OUTPUT_TOKENS`, `GEMINI_TIMEOUT_SECONDS` |
| Зависимости | [backend/pyproject.toml](../backend/pyproject.toml) | Добавлен `httpx>=0.27` в основные deps (Gemini REST-клиент) |
| ENV-пример | [.env.example](../.env.example) | Блок `GEMINI_*` со ссылкой на aistudio.google.com/app/apikey |

### Frontend

| Модуль | Файлы | Назначение |
|---|---|---|
| API-клиент | [frontend/src/api/ai.ts](../frontend/src/api/ai.ts) | Типы + методы `getSettings/updateSettings/listConversations/createConversation/sendMessage/archive/delete` |
| Pinia store | [frontend/src/stores/ai.ts](../frontend/src/stores/ai.ts) | `settings/conversations/currentConversation/messages/isWaitingForResponse` + методы |
| Главный чат | [frontend/src/views/ai/ChatView.vue](../frontend/src/views/ai/ChatView.vue) | Сайдбар бесед, шапка с выбором тона/сложности, лента сообщений, поле ввода, чип прикреплённых данных |
| Диалог прикрепления | [frontend/src/components/ai/AttachDataDialog.vue](../frontend/src/components/ai/AttachDataDialog.vue) | Вкладки «Профиль» / «Анализы» с превью |
| Главная | [frontend/src/views/HomeView.vue](../frontend/src/views/HomeView.vue) | Карточка «Иван Иваныч» с подсказкой и кнопкой «Открыть чат» |
| Меню | [frontend/src/components/AppNavigation.vue](../frontend/src/components/AppNavigation.vue) | Пункт «🤖 Иван Иваныч» активен, ведёт на `/ai/chat` |
| Анализ | [frontend/src/views/analyses/AnalysisDetailView.vue](../frontend/src/views/analyses/AnalysisDetailView.vue) | Кнопка «Спросить Ивана Иваныча» открывает чат с прикреплённым анализом и предзаполненным вопросом |
| Роутер | [frontend/src/router/index.ts](../frontend/src/router/index.ts) | `/ai/chat` (требует auth+profile) |
| Локализация | [frontend/src/locales/ru.json](../frontend/src/locales/ru.json) | Секция `ai.*` (тон, сложность, attach, ошибки), `home.ivan_hint`, `home.open_chat` |

### Тесты

| Файл | Покрытие |
|---|---|
| [backend/tests/unit/test_ai_safety_triggers.py](../backend/tests/unit/test_ai_safety_triggers.py) | 8+ паттернов suicide TP, 5 TN; 8 emergency TP, 5 TN; case-insensitive; пробелы. |
| [backend/tests/integration/test_ai.py](../backend/tests/integration/test_ai.py) | 13 тестов: defaults, PATCH settings, создание беседы, обычное сообщение с mock Gemini, suicide → canned + НЕ вызван Gemini, emergency → canned, изоляция беседы между пользователями, override tone/complexity в system prompt без записи в settings, attached профиль попадает в system prompt, timeout → 503, сортировка по updated_at DESC, архив, persist safety_event_type. |
| Mock Gemini | `FakeAIProvider` в [backend/tests/integration/conftest.py](../backend/tests/integration/conftest.py) — записывает все вызовы, чтобы можно было проверить, что safety-ответы НЕ вызывают провайдера. |

---

## 2. Архитектурные решения

### 2.1. Safety-проверка **перед** запросом в провайдер

В `AIService.send_message` regex-триггеры применяются ДО шифрования и ДО любых сетевых вызовов. Это даёт три гарантии:

1. Запрос с маркерами суицида/неотложного состояния **никогда** не уходит в сторонний сервис (Gemini, в будущем — OpenAI/Claude). Содержимое таких сообщений по определению чувствительное.
2. Ответ детерминирован — пользователь получает выверенный текст с конкретными телефонами (8-800-2000-122, 103, 112), а не вольный перевод от ИИ.
3. На этапе 12, когда подключим полные §8.12 категории, точка расширения — одна функция; никаких изменений в API/UI.

### 2.2. Один транзакционный коммит

Раньше я писал user_msg отдельным flush, потом дёргал провайдер, при ошибке делал rollback. Это работало, но было хрупким. Сейчас сценарий:

- safety: добавляем оба сообщения → commit.
- normal: вызываем провайдер; если ОК — добавляем оба сообщения → commit; если не ОК — никаких записей нет.

Таким образом, в БД никогда не остаётся «сиротский» user_msg без ответа от ассистента.

### 2.3. Шифрование контента сообщений

`ai_messages.content` и `ai_messages.attached_data` проходят через `EncryptionService`. На этапах 0–6 это identity-функция, но **код уже написан как «шифрует»** — на этапе 7 включение AES-GCM меняет только `ENCRYPTION_PROVIDER=aesgcm` в `.env`, без правок в `ai_service.py`. Без этого пришлось бы переписывать сервис.

Заголовок беседы (`title`) тоже шифруется — первые 50 символов первого сообщения могут содержать чувствительный медицинский контекст («Болит правый бок второй день…»).

### 2.4. История бесед — только последние 20 сообщений

Окно `_HISTORY_WINDOW = 20` (из подсказки этапа). Без ограничения долгие беседы быстро превысили бы бесплатный лимит токенов Gemini. Сообщения с `safety_event_type` исключаются из истории — они не должны влиять на дальнейший контекст разговора с моделью.

### 2.5. Manual-режим без полного доступа

Системный промпт явно говорит: «У тебя нет автоматического доступа к данным пользователя». Когда пользователь прикрепляет данные через UI, на сервере собирается JSON-снапшот (профиль + указанные анализы) и **вставляется в system prompt** под ключом `attached_data`. Сам JSON-снапшот тоже сохраняется в `ai_messages.attached_data` (шифрованно) — для прозрачности: в истории видно, какие данные были переданы.

Полный режим (`AIDataAccessMode.FULL`) уже есть в схеме, но не активирован — это §8.4 ТЗ и этап 12.

### 2.6. REST без SDK

GeminiProvider использует `httpx` напрямую. Причины:

- `google-generativeai` SDK тащит за собой gRPC, protobuf, дополнительные deps (~30 МБ).
- REST-API стабилен, документирован и не меняется так часто, как Python SDK.
- Контроль timeout/ретраев — наш, а не SDK.

### 2.7. Rate-limit 10 req/min на пользователя

`POST /ai/conversations/{id}/messages` под `@limiter.limit("10/minute")`. Это вписывается в бесплатный лимит Gemini (~15 req/min для `gemini-1.5-flash`) и защищает от bot-like поведения внутри одного аккаунта.

### 2.8. Override tone/complexity — без записи в БД

Пользователь меняет тон в шапке чата для **этого** запроса. В API уходит `override_tone`/`override_complexity`, в БД ничего не пишется. Если пользователь хочет сменить тон навсегда — в настройках `/ai/settings`. Это разделение явно сделано, чтобы UI шапки не «затирал» осознанный выбор пользователя в настройках.

---

## 3. Safety-покрытие и что отложено

### Реализовано (этап 5)

- ✅ §8.12.2.1 — suicide_risk (~18 паттернов)
- ✅ §8.12.2.2 — medical_emergency (~22 паттерна)
- ✅ Структурный лог `ai.safety_event` (без содержимого, только тип события и id)
- ✅ Маркировка `safety_event_type` в `ai_messages` (видна в UI красной рамкой)

### Отложено до этапа 12

- ❌ §8.12.3 — насилие в семье / над детьми / уязвимыми группами
- ❌ §8.12.4 — статьи УК РФ, незаконные вещества/действия
- ❌ §8.12.5 — prompt injection (попытка обойти системный промпт)
- ❌ Таблица `ai_safety_events` и admin-дашборд
- ❌ Pre/post-processing фильтры ответов модели
- ❌ ИИ-классификатор для семантической detection (regex покрывает очевидные случаи, но «я устал жить в этом мире» — пропустит)

**Текущий уровень — критический минимум.** Это явно отмечено в комментарии файла триггеров и в этом отчёте. Заказчик предупреждён.

---

## 4. Что НЕ сделано из этапного промпта (и почему)

Ничего из обязательного объёма этапа 5 не отложено. Реализованы все пункты §5.1–§5.9.

Не введено никаких сторонних UI-библиотек. Не реализованы OpenAI/Claude (явно отложены до v1.1 в промпте). Streaming через SSE — отложен на v1.1 (также по промпту).

---

## 5. Что нужно заказчику перед запуском

1. Получить **бесплатный** ключ Gemini API: https://aistudio.google.com/app/apikey
2. Положить его в `.env`:
   ```
   GEMINI_API_KEY=ваш_ключ
   ```
3. Перезапустить контейнеры: `docker compose up --build`.
4. Применить новую миграцию (выполнится автоматически на старте backend, но можно явно: `docker compose exec backend alembic upgrade head`).

Без ключа `/ai/chat` будет возвращать 503 на любое сообщение — это ожидаемое поведение в dev без живого Gemini.

---

## 6. Сценарий ручной проверки (DoD §1)

1. Залогиниться, в меню кликнуть «Иван Иваныч» → попасть на `/ai/chat`.
2. «Новая беседа» → написать «Привет, как ты?» → получить осмысленный ответ.
3. В шапке поменять тон на «Как энциклопедия» → написать «расскажи про холестерин» → ответ должен быть в сухом стиле.
4. Открыть один из анализов → нажать «Спросить Ивана Иваныча» → попасть в новый чат с прикреплённым чипом «Прикреплено: 1 анализ» и предзаполненным «Что значат эти результаты?».
5. Отправить → ответ учитывает данные анализа.
6. Написать «не хочу больше жить» → получить SUICIDE_RESPONSE_TEMPLATE с телефоном 8-800-2000-122. В логах backend (`docker compose logs backend | grep ai.safety_event`) — запись `event_type=suicide_risk`, **без** запроса к Gemini.

---

## 7. Известные проблемы / TODO

- 🟡 `TODO(этап 7)`: при подключении AES-GCM проверить, что `title` беседы корректно расшифровывается при смене ключа (повтор логина пересоздаёт ключ в Redis_keys).
- 🟡 `TODO(этап 9)`: добавить кэширование одинаковых запросов в Redis с TTL ~5 мин — снизит нагрузку на бесплатный Gemini.
- 🟡 `TODO(этап 12)`: расширить safety-каркас, заменить regex на семантический детектор.
- 🟡 `TODO(этап 12)`: режим «Полный доступ» (`AIDataAccessMode.FULL`) — поле уже есть, логики нет.
- 🟢 Дисклеймер про Telegram: ключ `ai.telegram_disclaimer` в `ru.json` уже добавлен — будет показываться на странице настроек ИИ в этапе 6, когда появится сама страница настроек.

---

## 8. Команда коммита

```
Этап 5: ИИ-помощник Иван Иваныч (базовая версия с Gemini)
```

Основное в теле коммита:
- backend: AIService + GeminiProvider + safety триггеры (suicide/emergency) + 13 integration + 6 unit тестов
- frontend: ChatView с тоном/сложностью, AttachDataDialog, переходы из анализов и главной
- migration `0005_ai_assistant`: три таблицы (ai_settings, ai_conversations, ai_messages)
- docs: ETAP_5_REPORT.md
