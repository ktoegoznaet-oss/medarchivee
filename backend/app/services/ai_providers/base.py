"""Abstract AI provider contract.

Currently only Gemini is implemented. The interface is intentionally
provider-agnostic so OpenAI/Claude can be plugged in later (v1.1) without
touching `AIService`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


# ---------- Exceptions ----------------------------------------------------- #


class AIProviderError(Exception):
    """Base class for AI provider failures."""


class RateLimitError(AIProviderError):
    """Quota / rate-limit exceeded (HTTP 429)."""


class AIServiceUnavailableError(AIProviderError):
    """Service unreachable / 5xx / timeout."""


class AIContentBlockedError(AIProviderError):
    """Provider refused to answer (safety filters, blocked categories)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------- DTOs ----------------------------------------------------------- #


@dataclass(frozen=True)
class AIMessage:
    """Message in the conversation history passed to the provider."""

    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class AIResponse:
    """Provider response surfaced to the service layer."""

    content: str
    tokens_used: int
    provider: str
    model: str


# ---------- Provider interface -------------------------------------------- #


class AIProvider(ABC):
    """Provider contract — one method, async, no streaming on stage 5."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[AIMessage],
        max_tokens: int = 1024,
    ) -> AIResponse:
        """Run a single completion and return the assistant message.

        Raises:
            RateLimitError: provider returned 429.
            AIServiceUnavailableError: timeout / 5xx / network error.
            AIContentBlockedError: provider blocked the request/response.
        """
