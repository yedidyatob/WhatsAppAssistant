from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4, UUID

from .models import ScheduledMessage, MessageStatus
from .repository import ScheduledMessageRepository
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

        # Idempotency check
        existing = self.repo.find_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        msg = ScheduledMessage(
            id=uuid4(),
            chat_id=chat_id,
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

    # ---------- Worker-facing API ----------

    def list_due_messages(self, limit: int = 10) -> list[ScheduledMessage]:
        now = self.clock()
        return self.repo.list_upcoming(now=now, limit=limit)

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

        if msg.status != MessageStatus.SCHEDULED:
            return

        if msg.send_at > now:
            return

        # Atomic lock
        locked = self.repo.lock_for_sending(msg_id, now)
        if not locked:
            return

        try:
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

class InboundMessageService:
    def __init__(
        self,
        message_repo: MessageRepository | None = None,
        job_repo: JobRepository | None = None,
    ):
        # Dependency injection friendly
        self.message_repo = message_repo or MessageRepository()
        self.job_repo = job_repo or JobRepository()
    def handle_inbound_event(
        self,
        *,
        message_id: str,
        chat_id: str,
        sender_id: str,
        text: Optional[str],
        timestamp: datetime,
        is_group: bool,
        raw: Optional[dict],
    ) -> tuple[bool, Optional[str]]:
        """
        Returns:
          (accepted, reason)
        accepted=False means:
          - safely ignored
          - no retry required
        """

        # 1️⃣ Idempotency guard
        if self.message_repo.exists(message_id):
            return False, "duplicate_message"

        # 2️⃣ Persist inbound message (always)
        self.message_repo.insert(
            message_id=message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            text=text,
            timestamp=timestamp,
            is_group=is_group,
            raw=raw,
        )

        # 3️⃣ Ignore empty / non-text messages
        if not text:
            return False, "no_text"

        text = text.strip()
        if not text:
            return False, "empty_text"

        # 4️⃣ Classify intent
        job_type = self._classify(text)

        if job_type is None:
            return False, "not_actionable"

        # 5️⃣ Enqueue job
        self.job_repo.enqueue(
            job_type=job_type,
            payload={
                "chat_id": chat_id,
                "sender_id": sender_id,
                "text": text,
                "source_message_id": message_id,
            },
        )

        return True, None

    def _classify(self, text: str) -> Optional[str]:
        """
        Maps text → job_type
        """

        t = text.lower()

        if t.startswith("schedule"):
            return "schedule_message"

        if t.startswith("cancel"):
            return "cancel_message"

        if t.startswith("list"):
            return "list_scheduled"

        return None


