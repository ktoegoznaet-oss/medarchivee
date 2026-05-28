"""Email subsystem: sender, templates, queue-aware service.

Layered API:

* `sender.py` — низкоуровневая отправка одного письма (aiosmtplib или
  log-fallback). Знает только о SMTP, не знает о шаблонах.
* `templates.py` — рендер HTML+plaintext через Jinja2.
* `service.py` — высокоуровневый EmailService: умеет ставить отправку
  в ARQ-очередь или (в тестах) отправлять сразу.

Бизнес-код вызывает только EmailService, низкоуровневые слои не трогает.
"""

from app.services.email.sender import EmailMessage, EmailSender, LogEmailSender, SmtpEmailSender
from app.services.email.service import EmailService
from app.services.email.templates import EmailTemplates, build_default_templates

__all__ = [
    "EmailMessage",
    "EmailSender",
    "EmailService",
    "EmailTemplates",
    "LogEmailSender",
    "SmtpEmailSender",
    "build_default_templates",
]
