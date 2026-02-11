from __future__ import annotations

from ..core.models import ScheduledMessage, MessageStatus


def row_to_scheduled_message(row) -> ScheduledMessage:
    return ScheduledMessage(
        id=row["id"],
        chat_id=row["chat_id"],
        from_chat_id=row.get("from_chat_id"),
        confirmation_message_id=row.get("confirmation_message_id"),
        text=row["text"],
        send_at=row["send_at"],
        status=MessageStatus(row["status"]),
        locked_at=row["locked_at"],
        sent_at=row["sent_at"],
        attempt_count=row["attempt_count"],
        last_error=row["last_error"],
        idempotency_key=row["idempotency_key"],
        source=row["source"],
        reason=row["reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
