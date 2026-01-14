from datetime import datetime, timezone
from uuid import UUID

import psycopg2
import psycopg2.extras

from ..core.models import ScheduledMessage, MessageStatus
from ..core.repository import ScheduledMessageRepository


LOCK_TIMEOUT_SECONDS = 300  # 5 minutes


class PostgresScheduledMessageRepository(ScheduledMessageRepository):
    def __init__(self, conn):
        self.conn = conn

    # ---------- helpers ----------

    def _row_to_model(self, row) -> ScheduledMessage:
        return ScheduledMessage(
            id=row["id"],
            chat_id=row["chat_id"],
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

    # ---------- interface ----------

    def create(self, msg: ScheduledMessage) -> None:
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheduled_messages (
                    id, chat_id, text, send_at, status,
                    locked_at, sent_at, attempt_count, last_error,
                    idempotency_key, source, reason,
                    created_at, updated_at
                )
                VALUES (
                    %(id)s, %(chat_id)s, %(text)s, %(send_at)s, %(status)s,
                    %(locked_at)s, %(sent_at)s, %(attempt_count)s, %(last_error)s,
                    %(idempotency_key)s, %(source)s, %(reason)s,
                    %(created_at)s, %(updated_at)s
                )
                """,
                msg.model_dump(),
            )

    def get(self, msg_id: UUID) -> ScheduledMessage | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM scheduled_messages WHERE id = %s",
                (msg_id,),
            )
            row = cur.fetchone()
            return self._row_to_model(row) if row else None

    def find_by_idempotency_key(self, key: str) -> ScheduledMessage | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM scheduled_messages WHERE idempotency_key = %s",
                (key,),
            )
            row = cur.fetchone()
            return self._row_to_model(row) if row else None

    def find_due(self, now: datetime, limit: int) -> list[ScheduledMessage]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM scheduled_messages
                WHERE status = 'SCHEDULED'
                  AND send_at <= %s
                ORDER BY send_at
                LIMIT %s
                """,
                (now, limit),
            )
            rows = cur.fetchall()
            return [self._row_to_model(r) for r in rows]

    def lock(self, msg_id: UUID, now: datetime) -> bool:
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduled_messages
                SET
                    status = 'LOCKED',
                    locked_at = %s,
                    updated_at = %s
                WHERE
                    id = %s
                    AND status = 'SCHEDULED'
                    AND (
                        locked_at IS NULL OR
                        locked_at < %s
                    )
                """,
                (
                    now,
                    now,
                    msg_id,
                    now.replace(tzinfo=timezone.utc)
                    - psycopg2.extensions.timedelta(seconds=LOCK_TIMEOUT_SECONDS),
                ),
            )
            return cur.rowcount == 1

    def mark_sent(self, msg_id: UUID, sent_at: datetime) -> None:
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduled_messages
                SET
                    status = 'SENT',
                    sent_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (sent_at, sent_at, msg_id),
            )

    def mark_failed(self, msg_id: UUID, error: str) -> None:
        now = datetime.now(timezone.utc)
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduled_messages
                SET
                    status = 'FAILED',
                    last_error = %s,
                    attempt_count = attempt_count + 1,
                    updated_at = %s
                WHERE id = %s
                """,
                (error, now, msg_id),
            )

    def cancel(self, msg_id: UUID) -> None:
        now = datetime.now(timezone.utc)
        with self.conn, self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduled_messages
                SET
                    status = 'CANCELLED',
                    updated_at = %s
                WHERE
                    id = %s
                    AND status != 'SENT'
                """,
                (now, msg_id),
            )




