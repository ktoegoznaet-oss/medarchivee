# Деплой МедАрхив

Инструкция по развёртыванию приложения на сервере (Debian, 3 CPU / 8 ГБ / 50 ГБ).

## Минимальные требования

- Docker 24+
- Docker Compose v2
- Открытый порт 80 (или 443 при настройке SSL через nginx)
- Доменное имя (для прода)

## Первый запуск

```bash
git clone <repo-url> /opt/medarchive
cd /opt/medarchive
cp .env.example .env
# отредактируй .env — см. ниже разделы про секреты и SMTP
docker compose up -d --build
docker compose logs -f backend  # проверь, что миграции прошли
```

## Обязательные секреты в `.env`

```env
APP_ENV=production
SECRET_KEY=<openssl rand -hex 32>
JWT_SECRET=<openssl rand -hex 32>
DB_ROOT_PASSWORD=<strong-password>
DB_PASSWORD=<strong-password>
```

В `APP_ENV=production` приложение **откажется стартовать**, если
`SECRET_KEY`/`JWT_SECRET` короче 32 символов или равны
`change-me-in-production-64-chars-min`. Если нужно сгенерировать ключи:
```bash
openssl rand -hex 32
```

## SMTP — Yandex (рекомендуется)

1. Завести / иметь почтовый ящик в Yandex (например, `noreply@yourdomain.ru`,
   если домен на Yandex 360, или `youremail@yandex.ru`).
2. Зайти в [id.yandex.ru/security](https://id.yandex.ru/security), раздел
   "Пароли приложений" → "Создать пароль приложения" → "Почта".
3. Сохранить полученный пароль приложения (16 символов).
4. Прописать в `.env`:
   ```env
   SMTP_HOST=smtp.yandex.ru
   SMTP_PORT=465
   SMTP_USER=youremail@yandex.ru
   SMTP_PASSWORD=<app-password-from-step-3>
   SMTP_FROM_EMAIL=youremail@yandex.ru
   SMTP_FROM_NAME=MedArchive
   SMTP_USE_SSL=True
   ```
5. Перезапустить `backend` и `mailer_worker`:
   ```bash
   docker compose restart backend mailer_worker
   ```
6. Проверить: зарегистрировать тестового пользователя, должно прийти письмо
   с кодом подтверждения. Если письмо не приходит — посмотри логи:
   ```bash
   docker compose logs mailer_worker --tail=50
   ```

В dev (`APP_ENV=development`) `SMTP_USER` можно оставить пустым — письма
пойдут в логи с событием `email.dev_fallback`. Удобно для локальной разработки
без настоящего почтового аккаунта.

## Первый администратор

```env
INITIAL_ADMIN_EMAIL=admin@yourdomain.ru
```

Зарегистрируйся через UI с этим email — роль `admin` будет назначена
автоматически (case-insensitive). Подробнее в [ADMIN_GUIDE.md](ADMIN_GUIDE.md).

## SSL / HTTPS

Сейчас приложение слушает на порту 80. Для прода:
- Поставить **Certbot** для Let's Encrypt:
  ```bash
  apt install certbot python3-certbot-nginx
  certbot --nginx -d medarchive.example.com
  ```
- Или вынести SSL за обратный прокси (например, Caddy / nginx на хосте).

Не забудь обновить `CORS_ORIGINS` и `FRONTEND_BASE_URL` в `.env` на
https-варианты.

## Шифрование (AES-256-GCM)

Активно начиная с Шага E (Спринт 2). По умолчанию `ENCRYPTION_PROVIDER=aesgcm`.

**ВАЖНО — `redis_keys` БЕЗ persistence:** контейнер `medarchive_redis_keys`
хранит DEK пользователей только в памяти. При его рестарте все активные
сессии получат 401 `session_key_lost` и потребуют повторного логина.
Это сделано намеренно — ключи никогда не уходят на диск, поэтому даже
компрометация бэкапа не даёт доступа к медданным.

При first-time setup или после смены пароля Argon2id даёт ~50мс задержку
на логин (OWASP L1). Если на боевом железе время отличается — настрой
`ARGON2_MEMORY_KIB`, `ARGON2_TIME_COST`, `ARGON2_PARALLELISM` в `.env`
после benchmark (цель — 50-250мс).

Подробнее: [ENCRYPTION.md](ENCRYPTION.md).

## Бэкап

Минимум, что нужно регулярно бэкапить:
- `mariadb_data` volume (включает все данные пользователей в зашифрованном
  виде; без `encrypted_dek` + пароля пользователя бэкап бесполезен —
  это **фича**, не баг)
- `.env` (секреты приложения — JWT, SMTP, БД-пароль)
- НЕ бэкапить `redis_keys` — он по дизайну эфемерный

Пример бэкапа MariaDB:
```bash
docker exec medarchive_mariadb mariadb-dump \
  -u root -p"$DB_ROOT_PASSWORD" medarchive | gzip > /backups/medarchive-$(date +%F).sql.gz
```

## Мониторинг

### Базовый (всегда работает)
- `docker compose logs -f` — структурные JSON-логи всех сервисов
- `docker stats` — потребление RAM/CPU
- Admin Telegram-бот (если настроен) — push'ит критические ошибки автоматически

### GlitchTip (Sentry-совместимый трекер ошибок)

Опциональный, но рекомендуется для прода. ~500MB RAM (полный Sentry — 5GB).

```bash
# 1. Сгенерировать секреты
echo "GLITCHTIP_POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env
echo "GLITCHTIP_SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 2. Запустить миграции и сервисы
docker compose -f docker-compose.glitchtip.yml up -d

# 3. Открыть http://localhost:8001 (или проксировать через nginx с basic-auth),
#    создать организацию, проект → получить DSN

# 4. Прописать DSN в основном .env и перезапустить backend
echo "SENTRY_DSN=https://<key>@<host>/<project>" >> .env
docker compose restart backend mailer_worker
```

**PII-фильтр уже встроен:** `backend/app/sentry_init.py:_before_send` удаляет
пароли, фразы, токены, шифротексты до отправки. Email маскируется до
`a***@b***.tld`.

## Размер дисков

Грубая оценка для 10 беты-пользователей:
- MariaDB: ~50 МБ + рост 1-5 МБ на пользователя в месяц
- Redis: ~50 МБ
- Логи backend/mailer_worker: ~10 МБ/день (с ротацией)

50 ГБ диска хватит на ~5 лет беты с запасом.
