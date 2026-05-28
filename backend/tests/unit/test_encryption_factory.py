"""Tests for the encryption-service DI factory."""

from __future__ import annotations

import pytest

from app import dependencies
from app.config import settings
from app.services.encryption_identity import IdentityEncryptionService


@pytest.fixture(autouse=True)
def _clear_factory_cache() -> None:
    """`lru_cache` would otherwise leak between tests changing the provider."""
    dependencies.reset_encryption_service_cache()
    yield
    dependencies.reset_encryption_service_cache()


def test_factory_returns_identity_when_provider_is_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "encryption_provider", "identity")

    svc = dependencies.get_encryption_service()

    assert isinstance(svc, IdentityEncryptionService)


def test_factory_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    # Bypass Pydantic Literal validation by patching the attribute directly.
    monkeypatch.setattr(settings, "encryption_provider", "rot13", raising=False)

    with pytest.raises(ValueError, match="Unknown ENCRYPTION_PROVIDER"):
        dependencies.get_encryption_service()
