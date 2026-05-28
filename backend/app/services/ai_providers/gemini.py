"""Google Gemini provider.

Uses the public REST API directly via httpx so we don't have to pull the
google-generativeai SDK (one less heavyweight dep + better control over
timeouts and retries).

Docs: https://ai.google.dev/api/rest/v1beta/models/generateContent
"""

from __future__ import annotations

import asyncio

import httpx
import structlog

from app.services.ai_providers.base import (
    AIContentBlockedError,
    AIMessage,
    AIProvider,
    AIResponse,
    AIServiceUnavailableError,
    RateLimitError,
)

log = structlog.get_logger(__name__)

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Все категории — на BLOCK_MEDIUM_AND_ABOVE. Согласно §8.12 ТЗ мы хотим, чтобы
# Gemini-сторона тоже фильтровала ответы; собственный safety-каркас идёт уже
# поверх (suicide/emergency проверки в AIService).
_SAFETY_SETTINGS: list[dict[str, str]] = [
    {"category": cat, "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
    for cat in (
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    )
]


class GeminiProvider(AIProvider):
    """Gemini implementation of :class:`AIProvider`."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.4,
        max_output_tokens: int = 1024,
        timeout_seconds: int = 30,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._timeout = timeout_seconds

    # ---- Public API ------------------------------------------------------ #

    async def generate(
        self,
        system_prompt: str,
        messages: list[AIMessage],
        max_tokens: int = 1024,
    ) -> AIResponse:
        payload = self._build_payload(system_prompt, messages, max_tokens)
        url = f"{_BASE_URL}/{self._model}:generateContent"

        try:
            data = await self._post_with_retry(url, payload)
        except httpx.TimeoutException as exc:
            log.warning("ai.gemini.timeout", model=self._model)
            raise AIServiceUnavailableError("Gemini timeout") from exc
        except httpx.HTTPError as exc:
            log.warning("ai.gemini.transport_error", error=str(exc))
            raise AIServiceUnavailableError(str(exc)) from exc

        return self._parse_response(data)

    # ---- HTTP ------------------------------------------------------------ #

    async def _post_with_retry(
        self, url: str, payload: dict[str, object]
    ) -> dict[str, object]:
        """POST once, retry exactly once on timeout (per spec §5.3)."""
        params = {"key": self._api_key}
        for attempt in (1, 2):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, params=params, json=payload)
            except httpx.TimeoutException:
                if attempt == 2:
                    raise
                log.info("ai.gemini.retry_after_timeout", attempt=attempt)
                await asyncio.sleep(0.5)
                continue

            self._raise_for_status(resp)
            return resp.json()

        # Defensive — the loop above either returns or raises.
        raise AIServiceUnavailableError("unreachable")

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 429:
            raise RateLimitError(
                "Бесплатный лимит Gemini исчерпан, попробуйте через минуту"
            )
        if resp.status_code == 503:
            raise AIServiceUnavailableError("Gemini временно недоступен")
        if resp.status_code == 400:
            # 400 у Gemini — это и валидация payload, и BLOCKED_REASON.
            try:
                body = resp.json()
            except ValueError:
                body = {}
            reason = self._extract_block_reason(body) or "bad_request"
            raise AIContentBlockedError(reason)
        if resp.status_code >= 500:
            raise AIServiceUnavailableError(f"Gemini {resp.status_code}")
        resp.raise_for_status()

    # ---- Payload --------------------------------------------------------- #

    def _build_payload(
        self,
        system_prompt: str,
        messages: list[AIMessage],
        max_tokens: int,
    ) -> dict[str, object]:
        # Gemini требует чередования user/model и НЕ принимает system role внутри
        # contents — для него есть отдельный systemInstruction.
        contents: list[dict[str, object]] = []
        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            contents.append(
                {"role": role, "parts": [{"text": msg.content}]}
            )

        return {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": min(max_tokens, self._max_output_tokens),
            },
            "safetySettings": _SAFETY_SETTINGS,
        }

    # ---- Response parsing ------------------------------------------------ #

    def _parse_response(self, data: dict[str, object]) -> AIResponse:
        candidates = data.get("candidates") or []
        if not isinstance(candidates, list) or not candidates:
            block_reason = self._extract_block_reason(data) or "no_candidates"
            raise AIContentBlockedError(block_reason)

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason") if isinstance(candidate, dict) else None
        if finish_reason in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT"}:
            raise AIContentBlockedError(str(finish_reason))

        text = self._extract_text(candidate)
        if not text:
            raise AIContentBlockedError("empty_response")

        usage = data.get("usageMetadata") or {}
        tokens = 0
        if isinstance(usage, dict):
            raw_tokens = usage.get("totalTokenCount", 0)
            try:
                tokens = int(raw_tokens)
            except (TypeError, ValueError):
                tokens = 0

        return AIResponse(
            content=text,
            tokens_used=tokens,
            provider="gemini",
            model=self._model,
        )

    @staticmethod
    def _extract_text(candidate: object) -> str:
        if not isinstance(candidate, dict):
            return ""
        content = candidate.get("content")
        if not isinstance(content, dict):
            return ""
        parts = content.get("parts")
        if not isinstance(parts, list):
            return ""
        chunks: list[str] = []
        for part in parts:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "".join(chunks).strip()

    @staticmethod
    def _extract_block_reason(body: dict[str, object]) -> str | None:
        feedback = body.get("promptFeedback")
        if isinstance(feedback, dict):
            reason = feedback.get("blockReason")
            if isinstance(reason, str):
                return reason
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
        return None
