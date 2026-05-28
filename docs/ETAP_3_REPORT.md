# Этап 3 — Отчёт

## Что готово

### Backend

**Модели** ([backend/app/models/patient_profile.py](backend/app/models/patient_profile.py)) — 5 таблиц + enum `AllergySeverity`:

- `patient_profiles` — все 🔒-поля как `Text` (FIO, дата рождения, пол, группа крови, рост, вес, контакты, страховка, город). `timezone` — открытый текст (нужен расписанию напоминаний с этапа 5+). `user_id` уникальный — один профиль на пользователя.
- `weight_history` — 🔒 weight_kg, note + recorded_at.
- `chronic_conditions` — 🔒 name, icd10_code, diagnosed_at, note + открытый `is_active`.
- `allergies` — 🔒 allergen, reaction, note + открытый `severity` (нужен UI-цвету и сортировке).
- `family_history` — 🔒 relation, condition, note.

Все FK на `users.id` с `ON DELETE CASCADE`. Все запросы фильтруются по `user_id` — пользователь A не видит данных B.

**Миграция** [0003_patient_profile.py](backend/migrations/versions/20260519_0003_patient_profile.py) создаёт все 5 таблиц со всеми FK и индексами по `user_id`.

**Сервисы** ([backend/app/services/](backend/app/services/)):

- `PatientProfileService` — `get_profile`, `create_profile`, `update_profile`, `add_weight_record`, `list_weight_history`. Возвращает DTO, расшифрованные. Помеченные 🔒-поля шифруются на записи, расшифровываются на чтении через `EncryptionService`. `add_weight_record` автоматически обновляет `weight_kg` в основном профиле.
- `ChronicConditionsService`, `AllergiesService`, `FamilyHistoryService` — стандартный CRUD с шифрованием 🔒-полей. Все методы фильтруют по `user_id`; `_get_owned` поднимает `*NotFoundError` если запись принадлежит другому пользователю.
- `DictionariesService` — поиск по in-memory JSON-справочнику МКБ-10 ([backend/app/data/icd10_ru.json](backend/app/data/icd10_ru.json), 113 кодов) с кэшированием в Redis на 1 час. Кэш — soft fallback: если Redis недоступен, сервис продолжает работать.

**API** ([backend/app/api/v1/profile.py](backend/app/api/v1/profile.py), [dictionaries.py](backend/app/api/v1/dictionaries.py)):

| Метод | Путь |
|---|---|
| GET/POST/PATCH | `/api/v1/profile` |
| GET/POST | `/api/v1/profile/weight-history` |
| GET/POST | `/api/v1/profile/chronic-conditions` |
| PATCH/DELETE | `/api/v1/profile/chronic-conditions/{id}` |
| GET/POST | `/api/v1/profile/allergies` |
| PATCH/DELETE | `/api/v1/profile/allergies/{id}` |
| GET/POST | `/api/v1/profile/family-history` |
| PATCH/DELETE | `/api/v1/profile/family-history/{id}` |
| GET | `/api/v1/dictionaries/icd10?search=&limit=` |

Все endpoints за `Depends(get_current_user)`.

**Pydantic-схемы** ([backend/app/schemas/profile.py](backend/app/schemas/profile.py)) с валидаторами: дата рождения в диапазоне 1900..сегодня; пол — enum; `height_cm` 30–250; `weight_kg` 1–500; `blood_type` ∈ {O/A/B/AB ± Rh}; `timezone` проверяется через `zoneinfo`.

**Тесты** ([backend/tests/integration/test_profile.py](backend/tests/integration/test_profile.py)) — 11 интеграционных тестов:
1. Создание профиля → 201
2. Двойное создание → 409
3. Будущая дата рождения → 422
4. GET без профиля → 404
5. Round-trip всех полей (включая UTF-8 кириллицу)
6. PATCH меняет только переданные поля
7. POST weight-history синхронизирует `weight_kg` в профиле
8. Изоляция: A не читает/обновляет/удаляет хронические B
9. Chronic CRUD round-trip с ICD-10 кодом
10. Поиск МКБ-10 по подстроке и по коду
11. Allergy create + delete round-trip

### Frontend

**Store** [stores/profile.ts](frontend/src/stores/profile.ts) — Pinia Composition API store: `profile`, `profileChecked`, `chronicConditions`, `allergies`, `weightHistory`. `fetchProfile()` при 404 ставит `profile=null, profileChecked=true` — это сигнал guard'у на onboarding.

**API-обёртки** [api/profile.ts](frontend/src/api/profile.ts) — типизированные методы для всех endpoints.

**Onboarding wizard** ([views/onboarding/OnboardingWizard.vue](frontend/src/views/onboarding/OnboardingWizard.vue)) — 3 шага через `v-stepper`:
- Шаг 1: ФИО, дата рождения, пол. Валидация: имя/фамилия непустые, дата ∈ 1900..сегодня.
- Шаг 2: рост, вес, группа крови, город. Часовой пояс — `Intl.DateTimeFormat().resolvedOptions().timeZone`, можно править.
- Шаг 3: добавление хронических (через `IcdAutocomplete` — `v-autocomplete` с debounce 250ms по `/dictionaries/icd10`) и аллергий со списком серьёзности.

После «Завершить» — `POST /profile` + создание всех набросков из шага 3 + редирект на `/`.

**Profile view** ([views/profile/ProfileView.vue](frontend/src/views/profile/ProfileView.vue)) — карточки: Основные данные, Физические параметры (с `WeightChart` через `vue-chartjs` при ≥ 2 записей веса), Контакты, Хронические заболевания, Аллергии. Диалоги для добавления / редактирования.

**Home dashboard** ([views/HomeView.vue](frontend/src/views/HomeView.vue)) — приветствие с именем, карточка-превью профиля, заглушки модулей этапов 4–6 с tooltip «Появится в следующем этапе».

**Боковое меню** ([components/AppNavigation.vue](frontend/src/components/AppNavigation.vue)) — `v-navigation-drawer` с Главной и Профилем активными; Анализы/Иван/Настройки — disabled с tooltip.

**Роутер** [router/index.ts](frontend/src/router/index.ts) — добавлен `requiresProfile`: если у залогиненного пользователя `profile === null`, guard перенаправляет на `/onboarding`. Routes `/onboarding`, `/profile`, `/` защищены `requiresAuth`.

**Локализация** [locales/ru.json](frontend/src/locales/ru.json) — все строки нового UI.

### Документация
- [docs/ENCRYPTION.md](docs/ENCRYPTION.md) — добавлен раздел «Этап 3 — первая проверка боем».

## Архитектурные решения

1. **Все 🔒-поля как `Text`, не `String(N)`.** AES-GCM ciphertext в base64 длиннее plaintext (на ~33% + nonce + tag). Если зафиксировать `String(255)`, длинная история болезни на этапе 7 не влезет. `Text` решает это сразу, и индексировать эти поля всё равно не имеет смысла.
2. **Числа как зашифрованный `Text`, не отдельный `Numeric`-столбец.** Хранение `height_cm` числом упростит SELECT'ы, но потребует двух разных путей шифрования (для текста и для чисел). Числа в Text унифицируют поток; конверсия — в сервисе.
3. **Расшифровка в сервисе, DTO в API.** Endpoint не знает про шифрование — это упрощает миграцию между провайдерами и тестирование. Это явное требование мастер-промпта §5.1.
4. **Изоляция через сервис, а не endpoint.** Все `*Service._get_owned(...)` фильтруют по `(id, user_id)`. Пользователь A не может ни прочитать, ни обновить, ни удалить запись B — даже если знает её `id`. Тест №8 подтверждает.
5. **`AllergySeverity` и `is_active` — не шифруются.** Severity нужен UI-цвету и сортировке (мы не хотим расшифровывать сотню записей, чтобы отсортировать по тяжести). Сам по себе `severe` без аллергена не идентифицирует диагноз — это метаданные.
6. **`timezone` — не шифруется.** Понадобится Celery-планировщику напоминаний (этап 5+) для расчёта времени отправки. Сам по себе таймзона не является медицинской тайной.
7. **DictionariesService с soft Redis fallback.** На текущем этапе и в тестах Redis может быть недоступен — справочник всё равно работает (читаем из JSON). На этапе 12 в проде Redis обязателен; тогда мы добавим `Settings.cache_required: bool`.
8. **`ICD10` autocomplete с debounce 250ms.** Минимальная задержка между нажатиями клавиш для разгрузки сервера. Поиск стартует только при `query.length >= 2`.
9. **Onboarding wizard 3 шага вместо 7.** Так требует этапный промпт. Полные 7 шагов из ТЗ §6.2 — нагрузка для пользователя без явной пользы в MVP. Если заказчик решит делать UX-исследование и захочет 7 шагов — это уже отдельная задача после этапа 11.
10. **Тесты — на in-memory SQLite, как в этапе 2.** Заявка про MariaDB-via-testcontainers переносится вместе с авто-Alembic из инфраструктурного апгрейда — после этапа 11 / перед этапом 12.

## Что отложено

| Что | Куда |
|-----|------|
| Загрузка файлов в `chronic_conditions` (выписки) | Этап 11 |
| Полный справочник МКБ-10 (≈14 000 кодов с подкатегориями) | Этап 11 |
| Менструальный цикл (§6.9.4 ТЗ) | Этап 11 |
| Семейные аккаунты (несколько пациентов на одного user) | Версия 1.2 (не в MVP) |
| Unit-тесты frontend (OnboardingWizard, ProfileView через Vitest) | Этап 11 (вместе с E2E через Playwright) |
| Полноценная страница Семейного анамнеза (UI) | Этап 11 (модель и API уже на месте) |

## Известные проблемы

- Frontend unit-тестов нет (промпт упоминает их как «базовые», но без полноценного browser-окружения у меня нет возможности их проверить). Все UI-компоненты type-checkable через `vue-tsc` — это покрывается шагом `frontend-build` в CI.
- `OnboardingWizard.vue` использует `v-stepper` с `template #item.N` — в Vuetify 3.7 этот синтаксис стабилен, но если заказчик обновит Vuetify до 3.8+ — может появиться deprecation warning. Безопасно мигрировать через `<v-stepper-window-item>` при апгрейде.
- `IcdAutocomplete` хранит query в локальном state и не дебаунсит ввод цифр (поиск по коду `J45` сработает сразу). Это сознательно: для коротких запросов короткая задержка.

## Что нужно сделать заказчику перед этапом 4

1. `docker compose down -v && docker compose up --build` (важно `-v`, чтобы переподнять БД с тремя миграциями подряд).
2. Сценарий вручную:
   - Зарегистрироваться → подтвердить email → войти.
   - Должен открыться onboarding (мастер настройки).
   - Заполнить 3 шага, добавить 1 хроническое + 1 аллергию.
   - Попасть на главную → видеть «Добрый день, {имя}!»
   - Открыть Профиль → все данные на месте.
   - Добавить ещё 1 запись веса → на странице профиля появляется график.
3. Если онбординг открывается каждый раз даже после заполнения — это бага в guard'е роутера: пришлите `docker compose logs backend` и скриншот консоли браузера.
