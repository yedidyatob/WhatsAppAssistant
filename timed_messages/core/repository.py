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
    def update_metadata(self, msg_id: UUID, message: ScheduledMessage) -> None: ...


class MessageRepository(ABC):
    """
    Stores inbound WhatsApp messages.

    Used for:
    - idempotency
    - audit trail
    - debugging
    """

    @abstractmethod
    def exists(self, message_id: str) -> bool:
        """
        Returns True if a message with this message_id
        was already persisted.
        """
        raise NotImplementedError

    @abstractmethod
    def insert(
        self,
        *,
        message_id: str,
        chat_id: str,
        sender_id: str,
        text: Optional[str],
        timestamp: datetime,
        is_group: bool,
        raw: Optional[Dict[str, Any]],
    ) -> None:
        """
        Persist an inbound message.

        Must be idempotent at the DB level
        (e.g. unique constraint on message_id).
        """
        raise NotImplementedError


class JobRepository(ABC):
    """
    Persistent job queue abstraction.
    """

    @abstractmethod
    def enqueue(
        self,
        *,
        job_type: str,
        payload: Dict[str, Any],
        run_at: Optional[datetime] = None,
    ) -> None:
        """
        Enqueue a job.

        If run_at is None, job is ready immediately.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_next(
        self,
        *,
        now: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch the next runnable job and mark it as claimed.

        Must be safe for multiple workers.
        """
        raise NotImplementedError

    @abstractmethod
    def mark_done(self, job_id: int) -> None:
        """
        Mark job as successfully completed.
        """
        raise NotImplementedError

    @abstractmethod
    def mark_failed(
        self,
        *,
        job_id: int,
        reason: str,
    ) -> None:
        """
        Mark job as failed.

        Retry logic is NOT handled here yet.
        """
        raise NotImplementedError
