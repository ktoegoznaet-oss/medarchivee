# Этап 4 — Отчёт

## Что готово

### Backend

**Модели** ([backend/app/models/analysis.py](../backend/app/models/analysis.py)):
- `AnalysisRecord` — `analysis_records`. Имена столбцов и таблиц по ТЗ v1.1 §5.3. `analysis_date` — **не** шифруется (нужно для сортировки и фильтра по диапазону). 🔒 `lab_name`, `doctor_referral`, `notes`. Индекс `(user_id, analysis_date)` для быстрого `list_records` с фильтром.
- `AnalysisValue` — `analysis_values`. `parameter_code` сознательно **не** шифруется (см. docstring файла) — без этого графики динамики невозможны. 🔒 `parameter_name`, `value`, `unit`, `reference_min`, `reference_max`. `user_id` дублируется в таблице значений для запроса истории одним SELECT без JOIN. Композитный индекс `(user_id, parameter_code, record_id)`.
- `AbnormalType` — enum `LOW | HIGH | NORMAL | UNKNOWN`.
- `record_id` и `user_id` имеют `ON DELETE CASCADE` — удаление записи или пользователя автоматически чистит все значения.

**Миграция** [`0004_analysis_records.py`](../backend/migrations/versions/20260519_0004_analysis_records.py) — 2 таблицы, 5 индексов, 2 FK с cascade.

**Справочник норм** [`backend/app/data/analysis_norms.json`](../backend/app/data/analysis_norms.json) — **52 параметра**. Каждый параметр имеет name_ru/name_en, единицы, alternative_units (для последующего парсинга единиц при OCR), категорию, описание, синонимы и список норм с разбивкой по полу и возрасту. Подробности — в [docs/MODULE_ANALYSES.md](MODULE_ANALYSES.md).

**Сервисы** ([backend/app/services/](../backend/app/services/)):
- `AnalysisNormsService` — загружает JSON через `@lru_cache`, отдаёт `ParameterDef`, `NormRange`. Поиск с soft Redis fallback (как `DictionariesService`). `get_norm(code, gender, age)` — точное соответствие пола приоритетнее `any`.
- `AnalysisService`:
  - `list_records(user_id, date_from, date_to, only_abnormal)` — фильтрует, считает summary (всего показателей + сколько вне нормы).
  - `get_record(user_id, id)` — с `selectinload(values)` для одного запроса.
  - `create_record(user_id, data)` — для каждого value: подтягивает норму из справочника при отсутствии (зная пол/возраст из профиля), запускает `calculate_abnormal`, шифрует 🔒-поля. Демография расшифровывается **один раз** для всей записи, а не на каждом value.
  - `update_record` — частичное обновление метаданных (без правок values).
  - `update_value(user_id, value_id, data)` — правит конкретное значение и пересчитывает `is_abnormal/abnormal_type` через расшифровку.
  - `delete_record` — cascade.
  - `get_parameter_history(user_id, parameter_code, date_from, date_to)` — основной метод для графика: возвращает массив точек `(date, value, value_numeric, ref_min, ref_max, is_abnormal, type)`, отсортированный по дате.
  - `_custom_code(parameter_name)` для значений без выбора из справочника — стабильный SHA1-префикс. Это позволяет строить график по «своему» параметру, если пользователь стабильно пишет одно и то же название.

**Утилита расчёта** [`app/utils/analysis_norm_calc.py`](../backend/app/utils/analysis_norm_calc.py) — `parse_number` (запятая, `<`, `>`, `≤`, `≥`) и `calculate_abnormal` с явной обработкой UNKNOWN при отсутствии норм или нечисловом значении.

**Pydantic-схемы** ([backend/app/schemas/analysis.py](../backend/app/schemas/analysis.py)) — `AnalysisRecordCreate/Update/Summary/Full`, `AnalysisValueInput/Response/Update`, `AnalysisHistoryResponse/Point`, dictionary-схемы.

**API** ([backend/app/api/v1/analyses.py](../backend/app/api/v1/analyses.py)) — 9 endpoints (записи + values + история + словарь параметров). Все за `Depends(get_current_user)`. Полная таблица — в [MODULE_ANALYSES.md](MODULE_ANALYSES.md).

**Тесты**:
- [tests/unit/test_norm_calc.py](../backend/tests/unit/test_norm_calc.py) — 11 unit-тестов парсера и логики.
- [tests/integration/test_analyses.py](../backend/tests/integration/test_analyses.py) — 13 интеграционных: создание с расчётом abnormal, авто-подстановка норм из словаря, текстовое значение → UNKNOWN, высокое значение → HIGH, листинг с фильтрами по дате и `only_abnormal`, изоляция пользователей (404 на чужой record), сортировка истории, патч значения с пересчётом, DELETE cascade, поиск по синониму «HGB», параметр-detail с гендерной нормой, фильтр по date_range.

### Frontend

**API + store**:
- [api/analyses.ts](../frontend/src/api/analyses.ts) — типизированные обёртки.
- [stores/analyses.ts](../frontend/src/stores/analyses.ts) — Pinia: `records`, `currentRecord`, `fetchList(filters)`, `fetchRecord`, `createRecord`, `deleteRecord`, `fetchParameterHistory`.

**Компоненты**:
- [ParameterAutocomplete.vue](../frontend/src/components/analyses/ParameterAutocomplete.vue) — `v-autocomplete` с debounce 250 ms по `/dictionaries/analysis-parameters`.
- [ParameterHistoryChart.vue](../frontend/src/components/analyses/ParameterHistoryChart.vue) — line chart с зелёной зоной нормы (chartjs-plugin-annotation) + переключатель «6 мес / 1 год / 5 лет / Всё».

**Views**:
- [AnalysesListView.vue](../frontend/src/views/analyses/AnalysesListView.vue) — список + сворачиваемая панель фильтров (даты + `only_abnormal`) + чип «N показателей, M вне нормы», красный при наличии отклонений.
- [AnalysisCreateView.vue](../frontend/src/views/analyses/AnalysisCreateView.vue) — форма с динамическим списком показателей. Выбор параметра подтягивает unit + norm (через `/dictionaries/analysis-parameters/{code}` с возрастом и полом из профиля). Поля редактируемы вручную.
- [AnalysisDetailView.vue](../frontend/src/views/analyses/AnalysisDetailView.vue) — таблица показателей с цветными иконками (🔴/🟡/🟢/⚪), кнопка «Динамика» открывает диалог с графиком, кнопка «Спросить Ивана Иваныча» disabled.

**Wiring**:
- В [AppNavigation.vue](../frontend/src/components/AppNavigation.vue) пункт «Анализы» теперь активен (ведёт на `/analyses`).
- [HomeView.vue](../frontend/src/views/HomeView.vue) показывает карточку «Последние анализы» (3 записи) + кнопку «Все анализы».
- [router/index.ts](../frontend/src/router/index.ts) — 3 новых route'а (`/analyses`, `/analyses/new`, `/analyses/:id`) под `requiresAuth + requiresProfile`.
- [locales/ru.json](../frontend/src/locales/ru.json) — раздел `analyses.*` + ключи для главной.
- [package.json](../frontend/package.json) — `chartjs-plugin-annotation@^3.1.0` добавлен.

### Документация
- [MODULE_ANALYSES.md](MODULE_ANALYSES.md) — справочник по модулю: содержимое словаря, как добавлять параметры, как работает расчёт abnormal, полная таблица API.
- [ETAP_4_REPORT.md](ETAP_4_REPORT.md) (этот файл).

## Архитектурные решения

1. **`parameter_code` НЕ шифруется.** Без открытого кода невозможно SELECT'ом получить временной ряд значений одного параметра — пришлось бы расшифровать **все** значения пользователя и фильтровать на стороне сервиса. Это бы убило производительность графиков при сотнях записей. Раскрытие «у пользователя есть запись «гемоглобин»» — приемлемый риск (сам параметр без значения не выдаёт диагноз).
2. **`parameter_name` шифруется, хотя `parameter_code` — нет.** Имя — лабораторный лейбл («Гемоглобин (HGB), Хеликс, методом X»). Это **больше** информации, чем `parameter_code = "hemoglobin"`: может выдать используемую лабораторию или конкретный набор параметров (например, расширенный гемостаз).
3. **`analysis_date` НЕ шифруется.** Аналогично §5: сортировка и диапазонные фильтры на ciphertext невозможны. Раскрытие «у пользователя есть какая-то запись в такой-то день» — приемлемо.
4. **Дублирование `user_id` в `analysis_values`.** История параметра — самый частый и тяжёлый запрос. Без дублирования пришлось бы делать JOIN на `analysis_records` для фильтра по пользователю. С дублированием — один индекс `(user_id, parameter_code, record_id)` и однотабличный SELECT. Целостность гарантирована двумя FK с `ON DELETE CASCADE`.
5. **Расчёт `is_abnormal` в момент записи и сохранение в БД.** Альтернатива — считать на лету при чтении. Преимущества хранения: `only_abnormal`-фильтр работает SQL'ом без декрипта; стабильность результата (если правила расчёта поменяются — старые записи не «перепрыгнут» в красную зону молча); `update_value` перерасчитывает явно, поэтому риск рассинхронизации минимальный.
6. **Демография пользователя расшифровывается один раз на запрос.** В `create_record` мы один раз вытаскиваем `gender` + `birth_date` из профиля. На каждом из 20 показателей дешифровывать заново — расточительно (на этапе 7 это сотни мс при AES + Redis-обращении за ключом).
7. **Авто-подстановка норм только при отсутствии явных.** Если пользователь сам ввёл `reference_min/max` — они приоритетны (например, ребёнок где-то рядом сдавал с другими нормами). Авто-подстановка — для типового сценария «не знаю норму, подставьте из справочника».
8. **Custom code для значений вне справочника.** SHA1 от `parameter_name.lower()`. Не криптографически — просто стабильный хэш для группировки в графиках. Это лучше, чем «нет графика» при ручном вводе.
9. **Тесты на in-memory SQLite.** Как этапы 2–3. Изоляция, round-trip, фильтры — всё работает. Сохраняется план перейти на MariaDB через testcontainers перед этапом 12.
10. **Цвета в UI на основе границ.** 🟡 «близко к норме» (в пределах ±5% от границы) — соответствует ТЗ §6.3.5. Это не отдельный backend-флаг, а вычисление на клиенте: backend отдаёт чистые `is_abnormal/abnormal_type`, frontend дополнительно подсвечивает «жёлтую зону» как UX-сигнал «обратите внимание, но это ещё не отклонение».

## Что отложено

| Что | На какой этап |
|-----|---------------|
| OCR PDF/изображений анализов | Этап 8 |
| Привязка анализа к эпизоду болезни | Этап 9 |
| «Спросить Ивана Иваныча» с контекстом анализа | Этап 5 |
| Расширение справочника до 200+ параметров | Постепенно после релиза |
| Множественный график (несколько параметров на одной оси) | Версия 1.1 |
| PDF/печатные формы анализа | Этап 12 |
| Пагинация списка | По мере необходимости после реального использования |

## Известные проблемы

- Frontend unit-тесты Vitest не добавлял (как в этапе 3) — есть только тип-проверка через `vue-tsc` в CI. Полный browser-тест появится с Playwright на этапе 11.
- `chartjs-plugin-annotation@^3.1.0` тянет ещё пару dev-deps при `npm install` — заказчику нужно пересобрать `frontend`: `docker compose build frontend` или `docker compose down && docker compose up --build`.
- `ParameterHistoryChart` строит зелёную зону нормы по **первой** точке, у которой есть `reference_min/max`. Если в массиве разные нормы (например, лаба сменила референс) — зона будет соответствовать самой ранней. Это сознательное упрощение: реальный «дрейф норм» решается на этапе 11 (добавим выбор лабы для отображения).
- `AnalysisCreateView` после успешного `submit` редиректит на список и не показывает success-снэк — добавлю на этапе 5 вместе с глобальным snackbar-store.

## Что нужно сделать заказчику перед этапом 5

1. `docker compose down -v && docker compose up --build` (с `-v` — переподнимется БД с 4 миграциями подряд) и `docker compose build frontend` (новая npm-зависимость).
2. Сценарий вручную:
   - Залогиниться → должен быть профиль (если нет — пройти онбординг этапа 3).
   - Открыть «Анализы» в левом меню.
   - «+ Добавить анализ» → дата вчерашняя, лаб «Инвитро».
   - 5 показателей: гемоглобин 135 (норма подтянется → зелёный), общий холестерин 6.4 (норма подтянется → красный, HIGH), ТТГ 0.2 (норма подтянется → красный, LOW), СРБ 12 без выбора параметра (UNKNOWN — нет норм), СОЭ 18.
   - Сохранить → попасть на список → строка «5 показателей, 2 вне нормы» красная.
   - Открыть запись → таблица с правильными цветами.
   - Добавить ещё одну запись с тем же гемоглобином (другая дата).
   - Открыть запись → «Динамика» на гемоглобине → видеть график с 2 точками и зелёной зоной 120–150 г/л.
3. Если расчёт abnormal расходится с ожиданием — посмотреть `docker compose logs backend | grep analyses` — там логируется `record_created` и `value_updated` с `user_id` (без значений).
