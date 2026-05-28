"""Factory that selects the concrete AI provider implementation.

Centralising provider construction here keeps `AIService` provider-agnostic
and lets tests swap a real Gemini client for a fake by overriding
`get_ai_provider_factory` in DI.
"""

from __future__ import annotations

from app.config import Settings
from app.models.ai import AIProvider as AIProviderEnum
from app.services.ai_providers.base import AIProvider
from app.services.ai_providers.gemini import GeminiProvider


class AIProviderFactory:
    """Returns the right :class:`AIProvider` for a given preferred provider."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self, preferred: AIProviderEnum) -> AIProvider:
        if preferred == AIProviderEnum.GEMINI:
            return GeminiProvider(
                api_key=self._settings.gemini_api_key,
                model=self._settings.gemini_model,
                temperature=self._settings.gemini_temperature,
                max_output_tokens=self._settings.gemini_max_output_tokens,
                timeout_seconds=self._settings.gemini_timeout_seconds,
            )
        # OpenAI / Claude — на v1.1. Пока — fallback на Gemini, чтобы не падать.
        raise NotImplementedError(
            f"Provider {preferred} wired in version 1.1"
        )
