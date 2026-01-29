from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from .models import ScheduledMessage


class ScheduledMessageRepository(ABC):

    @abstractmethod
    def create(self, msg: ScheduledMessage) -> None: ...

    @abstractmethod
    def get_by_id(self, msg_id: UUID) -> ScheduledMessage | None: ...

    @abstractmethod
    def list_upcoming(self, now: datetime, limit: int) -> list[ScheduledMessage]: ...

    @abstractmethod
    def list_scheduled(self, limit: int) -> list[ScheduledMessage]: ...

    @abstractmethod
    def lock_for_sending(self, msg_id: UUID, now: datetime) -> bool: ...

    @abstractmethod
    def mark_sent(self, msg_id: UUID, sent_at: datetime) -> None: ...

    @abstractmethod
    def mark_failed(self, msg_id: UUID, error: str) -> None: ...

    @abstractmethod
    def cancel(self, msg_id: UUID) -> None: ...

    @abstractmethod
    def find_by_idempotency_key(self, idempotency_key: str) -> ScheduledMessage | None: ...

    @abstractmethod
    def find_by_id_prefix(self, prefix: str, limit: int = 2) -> list[ScheduledMessage]: ...

    @abstractmethod
    def update_metadata(self, msg_id: UUID, message: ScheduledMessage) -> None: ...
