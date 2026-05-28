"""Jinja2-based email templates.

Для каждого письма — пара `*.html` и `*.txt`. Текстовая версия обязательна
(не все клиенты рендерят HTML, плюс SpamAssassin понижает балл за письма
без plaintext).

Шаблоны лежат в `templates/` рядом с этим модулем. Меняй их без правки
кода — Python подхватывает их через FileSystemLoader.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.email.sender import EmailMessage

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class _RenderedPair:
    subject: str
    text: str
    html: str


class EmailTemplates:
    """Высокоуровневые билдеры писем — по одному методу на тип письма.

    Каждый билдер принимает только бизнес-параметры (email, имя, код и т.п.),
    рендерит Jinja-шаблон и возвращает готовый EmailMessage.
    """

    def __init__(self, env: Environment) -> None:
        self._env = env

    def _render(self, template_basename: str, **context: Any) -> _RenderedPair:
        # Subject в HTML-шаблоне в первой строке `<!-- subject: ... -->`.
        # Это позволяет менять тему письма вместе с телом, в одном файле.
        html = self._env.get_template(f"{template_basename}.html").render(**context)
        text = self._env.get_template(f"{template_basename}.txt").render(**context)
        subject = self._extract_subject(html)
        # Из HTML-вывода убираем строку с маркером темы, чтобы она не попала
        # в письмо.
        html = self._strip_subject_marker(html)
        return _RenderedPair(subject=subject, text=text, html=html)

    @staticmethod
    def _extract_subject(html: str) -> str:
        marker = "<!-- subject:"
        end = "-->"
        start_idx = html.find(marker)
        if start_idx == -1:
            return "MedArchive"
        end_idx = html.find(end, start_idx)
        if end_idx == -1:
            return "MedArchive"
        return html[start_idx + len(marker) : end_idx].strip()

    @staticmethod
    def _strip_subject_marker(html: str) -> str:
        marker = "<!-- subject:"
        end = "-->"
        start_idx = html.find(marker)
        if start_idx == -1:
            return html
        end_idx = html.find(end, start_idx)
        if end_idx == -1:
            return html
        return (html[:start_idx] + html[end_idx + len(end) :]).lstrip()

    # ---- Public builders ------------------------------------------------- #

    def verify_email(
        self,
        *,
        to: str,
        code: str,
        username: str,
        frontend_base_url: str,
        ttl_hours: int,
    ) -> EmailMessage:
        rendered = self._render(
            "verify_email",
            code=code,
            username=username,
            frontend_base_url=frontend_base_url,
            ttl_hours=ttl_hours,
        )
        return EmailMessage(
            subject=rendered.subject,
            to=to,
            text=rendered.text,
            html=rendered.html,
        )

    def wipe_account(self, *, to: str, code: str) -> EmailMessage:
        rendered = self._render("wipe_account", code=code)
        return EmailMessage(
            subject=rendered.subject,
            to=to,
            text=rendered.text,
            html=rendered.html,
        )


def build_default_templates() -> EmailTemplates:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return EmailTemplates(env)
