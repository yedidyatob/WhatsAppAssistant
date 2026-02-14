from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
import re
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID

from .assistant_delivery import format_assistant_delivery
from .models import ScheduledMessage, MessageStatus
from .repository import ScheduledMessageRepository
from shared.runtime_config import assistant_mode_enabled

if TYPE_CHECKING:
    from ..transport.whatsapp import WhatsAppTransport


class TimedMessageService:
    def __init__(self, repo: ScheduledMessageRepository, clock=None):
        self.repo = repo
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ---------- Public API ----------

    def schedule_message(
        self,
        *,
        chat_id: str,
        from_chat_id: str | None = None,
        text: str,
        send_at: datetime,
        idempotency_key: str,
        source: str,
        reason: str | None = None,
    ) -> ScheduledMessage:
        now = self.clock()

        if send_at.tzinfo is None:
            raise ValueError("send_at must be timezone-aware (UTC)")

        if send_at <= now:
            raise ValueError("send_at must be in the future")

        if assistant_mode_enabled() and not from_chat_id:
            raise ValueError("from_chat_id required in assistant mode")

        # Idempotency check
        existing = self.repo.find_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        msg = ScheduledMessage(
            id=uuid4(),
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            text=text,
            send_at=send_at,
            status=MessageStatus.SCHEDULED,
            locked_at=None,
            sent_at=None,
            attempt_count=0,
            last_error=None,
            idempotency_key=idempotency_key,
            source=source,
            reason=reason,
            created_at=now,
            updated_at=now,
        )

        self.repo.create(msg)
        return msg

    def validate_assistant_schedule_window(
        self,
        *,
        send_at: datetime,
        now: datetime | None = None,
    ) -> None:
        if not assistant_mode_enabled():
            return

        current = now or self.clock()
        max_window = self._assistant_schedule_window()
        if send_at - current <= max_window:
            return

        hours = int(max_window.total_seconds() // 3600)
        raise ValueError(
            "Free version limit: I can only schedule within "
            f"{hours} hours in assistant mode. "
            "Long-range scheduling uses paid Meta messaging, and I'm working for free :/"
        )

    def _assistant_schedule_window(self) -> timedelta:
        value = os.getenv("WHATSAPP_ASSISTANT_MAX_SCHEDULE_HOURS", "24").strip()
        try:
            hours = int(value)
        except ValueError:
            hours = 24
        if hours <= 0:
            hours = 24
        return timedelta(hours=hours)

    def cancel_message(self, msg_id: UUID) -> None:
        msg = self.repo.get_by_id(msg_id)
        if not msg:
            return

        if msg.status == MessageStatus.SENT:
            raise ValueError("Cannot cancel a sent message")

        if msg.status == MessageStatus.CANCELLED:
            return

        self.repo.cancel(msg_id)

    def get_message(self, msg_id: UUID) -> ScheduledMessage | None:
        return self.repo.get_by_id(msg_id)

    def find_by_id_prefix(self, prefix: str) -> ScheduledMessage | None:
        matches = self.repo.find_by_id_prefix(prefix, limit=2)
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError("cancel id is ambiguous; please paste the full ID")
        return matches[0]

    # ---------- Worker-facing API ----------

    def list_due_messages(self, limit: int = 10) -> list[ScheduledMessage]:
        now = self.clock()
        return self.repo.list_upcoming(now=now, limit=limit)

    def list_scheduled_messages(self, limit: int = 10) -> list[ScheduledMessage]:
        return self.repo.list_scheduled(limit=limit)

    def list_scheduled_messages_for_sender(
        self,
        *,
        sender_id: str,
        limit: int = 10,
    ) -> list[ScheduledMessage]:
        normalized_sender = self._normalize_sender_id(sender_id)
        if not normalized_sender:
            return []
        return self.repo.list_scheduled_for_sender(
            normalized_sender_id=normalized_sender,
            limit=limit,
        )

    def find_by_id_prefix_for_sender(
        self,
        *,
        prefix: str,
        sender_id: str,
    ) -> ScheduledMessage | None:
        normalized_sender = self._normalize_sender_id(sender_id)
        if not normalized_sender:
            return None
        matches = self.repo.find_by_id_prefix_for_sender(
            prefix=prefix,
            normalized_sender_id=normalized_sender,
            limit=2,
        )
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError("cancel id is ambiguous; please paste the full ID")
        return matches[0]

    def set_confirmation_message_id(
        self,
        *,
        msg_id: UUID,
        confirmation_message_id: str,
    ) -> None:
        if not confirmation_message_id:
            return
        self.repo.set_confirmation_message_id(msg_id, confirmation_message_id)

    def find_scheduled_by_confirmation_message_id_for_sender(
        self,
        *,
        confirmation_message_id: str,
        sender_id: str,
    ) -> ScheduledMessage | None:
        normalized_sender = self._normalize_sender_id(sender_id)
        if not normalized_sender or not confirmation_message_id:
            return None
        return self.repo.find_scheduled_by_confirmation_message_id_for_sender(
            confirmation_message_id=confirmation_message_id,
            normalized_sender_id=normalized_sender,
        )

    def send_message_if_due(
        self,
        msg_id: UUID,
        transport: WhatsAppTransport,
        quoted_message_id: Optional[UUID],
    ) -> None:
        """
        send_func(chat_id: str, text: str, message_id: UUID) -> None
        """
        now = self.clock()
        msg = self.repo.get_by_id(msg_id)

        if not msg:
            return

        if msg.status in {
            MessageStatus.CANCELLED,
            MessageStatus.SENT,
            MessageStatus.FAILED,
        }:
            return

        if msg.send_at > now:
            return

        # Atomic lock
        locked = self.repo.lock_for_sending(msg_id, now)
        if not locked:
            return

        try:
            if assistant_mode_enabled():
                if not msg.from_chat_id:
                    raise ValueError("from_chat_id is required in assistant mode")
                delivery_text = format_assistant_delivery(msg)
                transport.send_message(
                    chat_id=msg.from_chat_id,
                    text=delivery_text,
                    message_id=msg.id,
                    quoted_message_id=quoted_message_id
                )
            else:
                transport.send_message(
                    chat_id=msg.chat_id,
                    text=msg.text,
                    message_id=msg.id,
                    quoted_message_id=quoted_message_id
                )
            self.repo.mark_sent(msg_id, sent_at=now)

        except Exception as e:
            self.repo.mark_failed(msg_id, error=str(e))
            raise

    def _normalize_sender_id(self, sender_id: str) -> str:
        digits = re.sub(r"\D", "", sender_id or "")
        return digits if digits else (sender_id or "").strip()
