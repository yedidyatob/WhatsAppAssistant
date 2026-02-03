from __future__ import annotations

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from timed_messages.db import Base
from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel


class MessageStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    LOCKED = "LOCKED"
    SENT = "SENT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ScheduledMessage(BaseModel):
    id: UUID
    chat_id: str
    from_chat_id: str | None = None
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


class ScheduledMessageRecord(Base):
    __tablename__ = "scheduled_messages"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    from_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        SAEnum(MessageStatus, name="message_status"),
        nullable=False,
        server_default=MessageStatus.SCHEDULED.value,
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_scheduled_messages_status_send_at", "status", "send_at"),
        Index("ix_scheduled_messages_send_at", "send_at"),
    )
