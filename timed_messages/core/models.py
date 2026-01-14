from typing import Any, Dict, Optional
from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field


class MessageStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    LOCKED = "LOCKED"
    SENT = "SENT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ScheduledMessage(BaseModel):
    id: UUID
    chat_id: str
    text: str

    send_at: datetime
    status: MessageStatus

    locked_at: datetime | None = None
    sent_at: datetime | None = None
    attempt_count: int = 0
    last_error: str | None = None

    idempotency_key: str
    source: str
    reason: str | None = None

    created_at: datetime
    updated_at: datetime
