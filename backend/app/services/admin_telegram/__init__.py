"""Admin Telegram subsystem.

Два независимых компонента:

* `notifier.py` — отправляет уведомления админу с любого участка backend
  (новые регистрации, тикеты, критические ошибки). Это httpx-based
  fire-and-forget вызов Telegram Bot API. Не требует aiogram, не
  требует отдельного процесса. Импортируется напрямую в auth/ticket
  сервисы.

* `bot.py` — отдельный долгоживущий процесс (контейнер `admin_telegram_bot`
  в docker-compose) с aiogram-handlers для команд /stats, /health, /help.
  Этот процесс ТОЛЬКО принимает входящие команды, не делает push.
"""

from app.services.admin_telegram.notifier import AdminNotifier, NullAdminNotifier

__all__ = ["AdminNotifier", "NullAdminNotifier"]
