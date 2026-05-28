"""Unit tests for EmailService — высокоуровневая отправка через очередь."""

from __future__ import annotations

from app.services.email import EmailMessage, EmailService, InProcessQueue
from app.services.email.templates import build_default_templates


class _RecordingSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


async def test_send_verification_code_enqueues_message_with_code() -> None:
    sender = _RecordingSender()
    service = EmailService(
        queue=InProcessQueue(sender),
        templates=build_default_templates(),
        frontend_base_url="http://localhost",
    )

    await service.send_verification_code(
        to="alice@example.com",
        code="654321",
        username="alice",
        ttl_hours=24,
    )

    assert len(sender.sent) == 1
    message = sender.sent[0]
    assert message.to == "alice@example.com"
    assert "654321" in message.text
    assert message.subject == "Подтверждение регистрации в МедАрхив"
