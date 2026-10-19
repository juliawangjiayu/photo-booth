"""Credential storage for local Photo Booth integrations.

Secrets must never fall back to SQLite or another plaintext file. Production
uses the operating system credential store through keyring; tests inject the
in-memory implementation below.
"""
from __future__ import annotations

from typing import Protocol


class SecretStore(Protocol):
    def get(self, name: str) -> str: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class KeyringSecretStore:
    service_name = "photo-booth"

    def get(self, name: str) -> str:
        import keyring

        return keyring.get_password(self.service_name, name) or ""

    def set(self, name: str, value: str) -> None:
        import keyring

        keyring.set_password(self.service_name, name, value)

    def delete(self, name: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(self.service_name, name)
        except PasswordDeleteError:
            pass


class MemorySecretStore:
    """Test double; never used as a runtime fallback."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, name: str) -> str:
        return self._values.get(name, "")

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> None:
        self._values.pop(name, None)


_secret_store: SecretStore | None = None


def get_secret_store() -> SecretStore:
    global _secret_store
    if _secret_store is None:
        _secret_store = KeyringSecretStore()
    return _secret_store
