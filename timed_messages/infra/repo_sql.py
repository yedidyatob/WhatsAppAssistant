from datetime import datetime, timezone, timedelta
from uuid import UUID

import psycopg2
import psycopg2.extras

from ..core.models import ScheduledMessage
from ..core.repository import ScheduledMessageRepository
from .repo_sql_mapper import row_to_scheduled_message
from .repo_sql_queries import (
    CANCEL_SQL,
    FIND_BY_CONFIRMATION_FOR_SENDER_SQL,
    FIND_BY_ID_PREFIX_FOR_SENDER_SQL,
    FIND_BY_ID_PREFIX_SQL,
    FIND_DUE_SQL,
    FIND_SCHEDULED_SQL,
    GET_BY_IDEMPOTENCY_SQL,
    GET_BY_ID_SQL,
    INSERT_MESSAGE_SQL,
    LIST_SCHEDULED_FOR_SENDER_SQL,
    LOCK_FOR_SENDING_SQL,
    MARK_FAILED_SQL,
    MARK_SENT_SQL,
    SET_CONFIRMATION_MESSAGE_ID_SQL,
    UPDATE_METADATA_SQL,
)


LOCK_TIMEOUT_SECONDS = 300  # 5 minutes


class PostgresScheduledMessageRepository(ScheduledMessageRepository):
    def __init__(self, conn):
        self.conn = conn

    # ---------- interface ----------

    def create(self, msg: ScheduledMessage) -> None:
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                INSERT_MESSAGE_SQL,
                msg.model_dump(),
            )

    def get(self, msg_id: UUID) -> ScheduledMessage | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                GET_BY_ID_SQL,
                (msg_id,),
            )
            row = cur.fetchone()
            return row_to_scheduled_message(row) if row else None

    def find_by_idempotency_key(self, key: str) -> ScheduledMessage | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                GET_BY_IDEMPOTENCY_SQL,
                (key,),
            )
            row = cur.fetchone()
            return row_to_scheduled_message(row) if row else None

    def find_by_id_prefix(self, prefix: str, limit: int = 2) -> list[ScheduledMessage]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                FIND_BY_ID_PREFIX_SQL,
                (f"{prefix}%", limit),
            )
            rows = cur.fetchall()
            return [row_to_scheduled_message(r) for r in rows]

    def find_by_id_prefix_for_sender(
        self,
        prefix: str,
        normalized_sender_id: str,
        limit: int = 2,
    ) -> list[ScheduledMessage]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                FIND_BY_ID_PREFIX_FOR_SENDER_SQL,
                (f"{prefix}%", normalized_sender_id, limit),
            )
            rows = cur.fetchall()
            return [row_to_scheduled_message(r) for r in rows]

    def find_due(self, now: datetime, limit: int) -> list[ScheduledMessage]:
        stale_before = now - timedelta(seconds=LOCK_TIMEOUT_SECONDS)
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                FIND_DUE_SQL,
                (now, now, stale_before, limit),
            )
            rows = cur.fetchall()
            return [row_to_scheduled_message(r) for r in rows]

    def find_scheduled(self, limit: int) -> list[ScheduledMessage]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                FIND_SCHEDULED_SQL,
                (limit,),
            )
            rows = cur.fetchall()
            return [row_to_scheduled_message(r) for r in rows]

    def list_scheduled_for_sender(
        self,
        normalized_sender_id: str,
        limit: int,
    ) -> list[ScheduledMessage]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                LIST_SCHEDULED_FOR_SENDER_SQL,
                (normalized_sender_id, limit),
            )
            rows = cur.fetchall()
            return [row_to_scheduled_message(r) for r in rows]

    def set_confirmation_message_id(
        self,
        msg_id: UUID,
        confirmation_message_id: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                SET_CONFIRMATION_MESSAGE_ID_SQL,
                (confirmation_message_id, now, msg_id),
            )

    def find_scheduled_by_confirmation_message_id_for_sender(
        self,
        confirmation_message_id: str,
        normalized_sender_id: str,
    ) -> ScheduledMessage | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                FIND_BY_CONFIRMATION_FOR_SENDER_SQL,
                (confirmation_message_id, normalized_sender_id),
            )
            row = cur.fetchone()
            return row_to_scheduled_message(row) if row else None

    def lock(self, msg_id: UUID, now: datetime) -> bool:
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                LOCK_FOR_SENDING_SQL,
                (
                    now,
                    now,
                    msg_id,
                    now - timedelta(seconds=LOCK_TIMEOUT_SECONDS),
                ),
            )
            return cur.rowcount == 1

    def mark_sent(self, msg_id: UUID, sent_at: datetime) -> None:
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                MARK_SENT_SQL,
                (sent_at, sent_at, msg_id),
            )

    def mark_failed(self, msg_id: UUID, error: str) -> None:
        now = datetime.now(timezone.utc)
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                MARK_FAILED_SQL,
                (error, now, msg_id),
            )

    def cancel(self, msg_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                CANCEL_SQL,
                (now, msg_id),
            )

    def get_by_id(self, msg_id: UUID) -> ScheduledMessage | None:
        return self.get(msg_id)

    def list_upcoming(self, now: datetime, limit: int) -> list[ScheduledMessage]:
        return self.find_due(now, limit)

    def list_scheduled(self, limit: int) -> list[ScheduledMessage]:
        return self.find_scheduled(limit)

    def lock_for_sending(self, msg_id: UUID, now: datetime) -> bool:
        return self.lock(msg_id, now)

    def update_metadata(self, msg_id: UUID, message: ScheduledMessage) -> None:
        payload = message.model_dump()
        payload["id"] = msg_id
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                UPDATE_METADATA_SQL,
                payload,
            )
