#!/usr/bin/env bash
#
# Скрипт первичной настройки локального dev-окружения.
#
#  * Создаёт .env из шаблона, если его нет.
#  * Генерирует случайные SECRET_KEY и JWT_SECRET через openssl,
#    чтобы заводские «change-me» не попали в живые токены.
#  * Не трогает живые секреты (GEMINI_API_KEY, TELEGRAM_BOT_TOKEN) —
#    их нужно заполнить вручную.
#
# Использование:
#   bash scripts/init-dev.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
ENV_EXAMPLE="${ROOT_DIR}/.env.example"

if [ ! -f "${ENV_EXAMPLE}" ]; then
  echo "Не найден ${ENV_EXAMPLE}. Запускай скрипт из корня репозитория." >&2
  exit 1
fi

if [ -f "${ENV_FILE}" ]; then
  echo "Файл .env уже существует — пропускаю генерацию."
  echo "Если хочешь пересоздать, удали .env вручную и перезапусти скрипт."
  exit 0
fi

cp "${ENV_EXAMPLE}" "${ENV_FILE}"
echo "Создан ${ENV_FILE}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl не найден — секреты остались дефолтными." >&2
  echo "Сгенерируй вручную и подставь в .env:" >&2
  echo "  python -c 'import secrets; print(secrets.token_hex(32))'" >&2
  exit 0
fi

# Кросс-платформенный sed (Linux/macOS используют разный синтаксис -i).
sed_inplace() {
  if [ "$(uname)" = "Darwin" ]; then
    sed -i "" "$@"
  else
    sed -i "$@"
  fi
}

SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)

sed_inplace "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" "${ENV_FILE}"
sed_inplace "s|^JWT_SECRET=.*|JWT_SECRET=${JWT_SECRET}|" "${ENV_FILE}"

echo "SECRET_KEY и JWT_SECRET сгенерированы случайными значениями."
echo
echo "Что ещё надо заполнить вручную:"
echo "  - GEMINI_API_KEY (https://aistudio.google.com/app/apikey)"
echo "  - TELEGRAM_BOT_TOKEN + TELEGRAM_BOT_USERNAME (через @BotFather)"
echo
echo "Готово. Дальше: docker compose up --build"
