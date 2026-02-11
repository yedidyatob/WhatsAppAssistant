from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets
from typing import Protocol


class AuthCodeGenerator(Protocol):
    def generate(self) -> str:
        ...


class SixDigitAuthCodeGenerator:
    def generate(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"


@dataclass(frozen=True)
class PendingAuthEntry:
    code: str
    updated_at: datetime


class PendingAuthStore(Protocol):
    def get(self, key: str, now: datetime) -> PendingAuthEntry | None:
        ...

    def set(self, key: str, code: str, now: datetime) -> None:
        ...

    def clear(self, key: str) -> None:
        ...


class InMemoryPendingAuthStore:
    def __init__(self, ttl: timedelta) -> None:
        self._ttl = ttl
        self._entries: dict[str, PendingAuthEntry] = {}

    def get(self, key: str, now: datetime) -> PendingAuthEntry | None:
        entry = self._entries.get(key)
        if not entry:
            return None
        if now - entry.updated_at > self._ttl:
            self._entries.pop(key, None)
            return None
        return entry

    def set(self, key: str, code: str, now: datetime) -> None:
        self._entries[key] = PendingAuthEntry(code=code, updated_at=now)

    def clear(self, key: str) -> None:
        self._entries.pop(key, None)
