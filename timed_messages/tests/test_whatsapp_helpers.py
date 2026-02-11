from datetime import datetime, timezone
from uuid import uuid4

import pytest

from timed_messages.core.models import MessageStatus
from timed_messages.core.whatsapp_formatting import format_list_reply, format_schedule_reply, format_when_prompt
from timed_messages.core.whatsapp_normalization import extract_id_prefix, normalize_contact_phone, normalize_recipient
from timed_messages.core.whatsapp_time import parse_datetime
from timed_messages.infra.repo_sql_mapper import row_to_scheduled_message


def test_normalize_recipient_and_contact_phone():
    assert normalize_recipient("+1 (555) 222-3333", None) == "15552223333@s.whatsapp.net"
    assert normalize_recipient("15552223333@s.whatsapp.net", None) == "15552223333@s.whatsapp.net"
    assert normalize_recipient("", "15552223333") == "15552223333@s.whatsapp.net"

    assert normalize_contact_phone(["+1 555 222 3333", "1-555-222-3333"]) == ("15552223333", None)
    assert normalize_contact_phone(["15552223333", "15553334444"]) == (None, "multiple_numbers")


def test_extract_id_prefix():
    assert extract_id_prefix("cancel abcdef123456 please") == "abcdef123456"
    assert extract_id_prefix("no id here") is None


def test_parse_datetime_variants():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    hhmm = parse_datetime("13:30", "UTC", now)
    assert hhmm.hour == 13 and hhmm.minute == 30

    tomorrow = parse_datetime("tomorrow 08:15", "UTC", now)
    assert tomorrow.day == 2 and tomorrow.hour == 8

    absolute = parse_datetime("2024-01-02 09:00", "UTC", now)
    assert absolute.year == 2024 and absolute.day == 2 and absolute.hour == 9


def test_formatting_helpers():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    msg = row_to_scheduled_message(
        {
            "id": uuid4(),
            "chat_id": "15552223333@s.whatsapp.net",
            "from_chat_id": "15551112222@s.whatsapp.net",
            "confirmation_message_id": None,
            "text": "hello world",
            "send_at": now,
            "status": "SCHEDULED",
            "locked_at": None,
            "sent_at": None,
            "attempt_count": 0,
            "last_error": None,
            "idempotency_key": "k",
            "source": "whatsapp",
            "reason": None,
            "created_at": now,
            "updated_at": now,
        }
    )
    prompt = format_when_prompt("UTC")
    assert "Current time zone: UTC" in prompt

    schedule = format_schedule_reply(
        scheduled_id=str(msg.id),
        to_value=msg.chat_id,
        send_at=msg.send_at,
        tz_name="UTC",
    )
    assert "✅ Scheduled" in schedule

    listed = format_list_reply([msg], tz_name="UTC")
    assert "✅ Scheduled messages" in listed


def test_row_to_scheduled_message_maps_status():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    mapped = row_to_scheduled_message(
        {
            "id": uuid4(),
            "chat_id": "1@s.whatsapp.net",
            "from_chat_id": None,
            "confirmation_message_id": None,
            "text": "x",
            "send_at": now,
            "status": "SENT",
            "locked_at": None,
            "sent_at": now,
            "attempt_count": 1,
            "last_error": None,
            "idempotency_key": "idemp",
            "source": "test",
            "reason": "r",
            "created_at": now,
            "updated_at": now,
        }
    )
    assert mapped.status == MessageStatus.SENT


def test_parse_datetime_requires_tz():
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        parse_datetime("13:30", None, now)
