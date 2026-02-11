INSERT_MESSAGE_SQL = """
INSERT INTO scheduled_messages (
    id, chat_id, from_chat_id, confirmation_message_id, text, send_at, status,
    locked_at, sent_at, attempt_count, last_error,
    idempotency_key, source, reason,
    created_at, updated_at
)
VALUES (
    %(id)s, %(chat_id)s, %(from_chat_id)s, %(confirmation_message_id)s, %(text)s, %(send_at)s, %(status)s,
    %(locked_at)s, %(sent_at)s, %(attempt_count)s, %(last_error)s,
    %(idempotency_key)s, %(source)s, %(reason)s,
    %(created_at)s, %(updated_at)s
)
"""

GET_BY_ID_SQL = "SELECT * FROM scheduled_messages WHERE id = %s"
GET_BY_IDEMPOTENCY_SQL = "SELECT * FROM scheduled_messages WHERE idempotency_key = %s"

FIND_BY_ID_PREFIX_SQL = """
SELECT *
FROM scheduled_messages
WHERE REPLACE(id::text, '-', '') LIKE %s
ORDER BY created_at DESC
LIMIT %s
"""

FIND_BY_ID_PREFIX_FOR_SENDER_SQL = """
SELECT *
FROM scheduled_messages
WHERE
    REPLACE(id::text, '-', '') LIKE %s
    AND regexp_replace(COALESCE(from_chat_id, ''), '[^0-9]', '', 'g') = %s
ORDER BY created_at DESC
LIMIT %s
"""

FIND_DUE_SQL = """
SELECT *
FROM scheduled_messages
WHERE (
    status = 'SCHEDULED'
    AND send_at <= %s
) OR (
    status = 'LOCKED'
    AND send_at <= %s
    AND (locked_at IS NULL OR locked_at < %s)
)
ORDER BY send_at
LIMIT %s
"""

FIND_SCHEDULED_SQL = """
SELECT *
FROM scheduled_messages
WHERE status = 'SCHEDULED'
ORDER BY send_at
LIMIT %s
"""

LIST_SCHEDULED_FOR_SENDER_SQL = """
SELECT *
FROM scheduled_messages
WHERE
    status = 'SCHEDULED'
    AND regexp_replace(COALESCE(from_chat_id, ''), '[^0-9]', '', 'g') = %s
ORDER BY send_at
LIMIT %s
"""

SET_CONFIRMATION_MESSAGE_ID_SQL = """
UPDATE scheduled_messages
SET
    confirmation_message_id = %s,
    updated_at = %s
WHERE id = %s
"""

FIND_BY_CONFIRMATION_FOR_SENDER_SQL = """
SELECT *
FROM scheduled_messages
WHERE
    confirmation_message_id = %s
    AND status IN ('SCHEDULED', 'LOCKED')
    AND regexp_replace(COALESCE(from_chat_id, ''), '[^0-9]', '', 'g') = %s
ORDER BY created_at DESC
LIMIT 1
"""

LOCK_FOR_SENDING_SQL = """
UPDATE scheduled_messages
SET
    status = 'LOCKED',
    locked_at = %s,
    updated_at = %s
WHERE
    id = %s
    AND (
        status = 'SCHEDULED'
        OR (
            status = 'LOCKED'
            AND (locked_at IS NULL OR locked_at < %s)
        )
    )
"""

MARK_SENT_SQL = """
UPDATE scheduled_messages
SET
    status = 'SENT',
    sent_at = %s,
    updated_at = %s
WHERE id = %s
"""

MARK_FAILED_SQL = """
UPDATE scheduled_messages
SET
    status = 'FAILED',
    last_error = %s,
    attempt_count = attempt_count + 1,
    updated_at = %s
WHERE id = %s
"""

CANCEL_SQL = """
UPDATE scheduled_messages
SET
    status = 'CANCELLED',
    updated_at = %s
WHERE
    id = %s
    AND status != 'SENT'
"""

UPDATE_METADATA_SQL = """
UPDATE scheduled_messages
SET
    chat_id = %(chat_id)s,
    from_chat_id = %(from_chat_id)s,
    confirmation_message_id = %(confirmation_message_id)s,
    text = %(text)s,
    send_at = %(send_at)s,
    status = %(status)s,
    locked_at = %(locked_at)s,
    sent_at = %(sent_at)s,
    attempt_count = %(attempt_count)s,
    last_error = %(last_error)s,
    idempotency_key = %(idempotency_key)s,
    source = %(source)s,
    reason = %(reason)s,
    updated_at = %(updated_at)s
WHERE id = %(id)s
"""
