from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import pytest

from timed_messages.core.models import MessageStatus, ScheduledMessage


@dataclass
class FakeRepo:
    messages: dict[UUID, ScheduledMessage] = field(default_factory=dict)

    def create(self, msg: ScheduledMessage) -> None:
        self.messages[msg.id] = msg

    def get_by_id(self, msg_id: UUID) -> ScheduledMessage | None:
        return self.messages.get(msg_id)

    def list_upcoming(self, now: datetime, limit: int) -> list[ScheduledMessage]:
        return [
            msg
            for msg in self._sorted_messages()
            if msg.status == MessageStatus.SCHEDULED and msg.send_at <= now
        ][:limit]

    def list_scheduled(self, limit: int) -> list[ScheduledMessage]:
        return [
            msg for msg in self._sorted_messages()
            if msg.status == MessageStatus.SCHEDULED
        ][:limit]

    def lock_for_sending(self, msg_id: UUID, now: datetime) -> bool:
        msg = self.messages.get(msg_id)
        if not msg or msg.status != MessageStatus.SCHEDULED:
            return False
        self.messages[msg_id] = msg.model_copy(
            update={"status": MessageStatus.LOCKED, "locked_at": now}
        )
        return True

    def mark_sent(self, msg_id: UUID, sent_at: datetime) -> None:
        msg = self.messages[msg_id]
        self.messages[msg_id] = msg.model_copy(
            update={
                "status": MessageStatus.SENT,
                "sent_at": sent_at,
                "updated_at": sent_at,
            }
        )

    def mark_failed(self, msg_id: UUID, error: str) -> None:
        msg = self.messages[msg_id]
        self.messages[msg_id] = msg.model_copy(
            update={
                "status": MessageStatus.FAILED,
                "last_error": error,
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def cancel(self, msg_id: UUID) -> None:
        msg = self.messages[msg_id]
        self.messages[msg_id] = msg.model_copy(update={"status": MessageStatus.CANCELLED})

    def find_by_idempotency_key(self, idempotency_key: str) -> ScheduledMessage | None:
        for msg in self.messages.values():
            if msg.idempotency_key == idempotency_key:
                return msg
        return None

    def find_by_id_prefix(self, prefix: str, limit: int = 2) -> list[ScheduledMessage]:
        return [msg for msg in self._sorted_messages() if msg.id.hex.startswith(prefix)][:limit]

    def find_by_id_prefix_for_sender(
        self,
        prefix: str,
        normalized_sender_id: str,
        limit: int = 2,
    ) -> list[ScheduledMessage]:
        return [
            msg
            for msg in self._sorted_messages()
            if msg.id.hex.startswith(prefix)
            and self._normalize_sender(msg) == normalized_sender_id
        ][:limit]

    def list_scheduled_for_sender(
        self,
        normalized_sender_id: str,
        limit: int,
    ) -> list[ScheduledMessage]:
        return [
            msg
            for msg in self._sorted_messages()
            if msg.status == MessageStatus.SCHEDULED
            and self._normalize_sender(msg) == normalized_sender_id
        ][:limit]

    def set_confirmation_message_id(self, msg_id: UUID, confirmation_message_id: str) -> None:
        msg = self.messages[msg_id]
        self.messages[msg_id] = msg.model_copy(
            update={"confirmation_message_id": confirmation_message_id}
        )

    def find_scheduled_by_confirmation_message_id_for_sender(
        self,
        confirmation_message_id: str,
        normalized_sender_id: str,
    ) -> ScheduledMessage | None:
        for msg in self._sorted_messages():
            if (
                msg.confirmation_message_id == confirmation_message_id
                and self._normalize_sender(msg) == normalized_sender_id
            ):
                return msg
        return None

    def update_metadata(self, msg_id: UUID, message: ScheduledMessage) -> None:
        self.messages[msg_id] = message

    def _sorted_messages(self) -> Iterable[ScheduledMessage]:
        return sorted(self.messages.values(), key=lambda msg: msg.send_at)

    def _normalize_sender(self, msg: ScheduledMessage) -> str:
        value = msg.from_chat_id or msg.chat_id
        digits = "".join(ch for ch in value if ch.isdigit())
        return digits if digits else value


@dataclass
class FakeTransport:
    sent: list[dict[str, object]] = field(default_factory=list)

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        message_id: UUID | None = None,
        quoted_message_id: str | None = None,
    ) -> str:
        self.sent.append(
            {
                "chat_id": chat_id,
                "text": text,
                "message_id": message_id,
                "quoted_message_id": quoted_message_id,
            }
        )
        return "confirmation-id"


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def fake_repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def fake_transport() -> FakeTransport:
    return FakeTransport()
