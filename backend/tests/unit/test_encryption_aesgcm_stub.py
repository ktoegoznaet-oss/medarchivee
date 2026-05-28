"""Tests for the AES-GCM scaffold — every method must raise until stage 7."""

from __future__ import annotations

import inspect

import pytest

from app.services.encryption_aesgcm import AESGCMEncryptionService
from app.services.encryption_service import EncryptionService


@pytest.fixture
def svc() -> AESGCMEncryptionService:
    return AESGCMEncryptionService(redis_keys_client=None, argon2_params={})


async def test_all_methods_raise_not_implemented(svc: AESGCMEncryptionService) -> None:
    with pytest.raises(NotImplementedError):
        await svc.encrypt("x", user_id=1)
    with pytest.raises(NotImplementedError):
        await svc.decrypt("x", user_id=1)
    with pytest.raises(NotImplementedError):
        await svc.derive_user_key("pw", b"\x00" * 32)
    with pytest.raises(NotImplementedError):
        await svc.store_session_key(1, "s", b"\x00" * 32, 900)
    with pytest.raises(NotImplementedError):
        await svc.get_session_key(1, "s")
    with pytest.raises(NotImplementedError):
        await svc.revoke_session_key(1, "s")
    with pytest.raises(NotImplementedError):
        await svc.encrypt_with_key("x", b"\x00" * 32)
    with pytest.raises(NotImplementedError):
        await svc.decrypt_with_key("x", b"\x00" * 32)


async def test_not_implemented_message_mentions_stage_7(svc: AESGCMEncryptionService) -> None:
    with pytest.raises(NotImplementedError) as exc_info:
        await svc.encrypt("x", user_id=1)
    assert "этапе 7" in str(exc_info.value)


def test_scaffold_satisfies_encryption_service_interface(
    svc: AESGCMEncryptionService,
) -> None:
    # Scaffold is concrete enough to instantiate (no abstract methods remain),
    # and structurally fits the interface contract.
    assert isinstance(svc, EncryptionService)
    interface_methods = {
        name
        for name, _ in inspect.getmembers(EncryptionService, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert interface_methods.issubset(
        {name for name, _ in inspect.getmembers(svc, predicate=inspect.ismethod)}
    )
