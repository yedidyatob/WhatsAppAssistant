from datetime import datetime, timezone
from uuid import uuid4

from timed_messages.core.assistant_delivery import build_whatsapp_link, format_assistant_delivery
from timed_messages.core.models import MessageStatus, ScheduledMessage


def _msg(chat_id: str, text: str) -> ScheduledMessage:
    now = datetime.now(timezone.utc)
    return ScheduledMessage(
        id=uuid4(),
        chat_id=chat_id,
        from_chat_id="111@s.whatsapp.net",
        text=text,
        send_at=now,
        status=MessageStatus.SCHEDULED,
        idempotency_key="k",
        source="test",
        created_at=now,
        updated_at=now,
    )


def test_build_whatsapp_link_encodes_text_and_digits():
    link = build_whatsapp_link("+1 (555) 222-3333@s.whatsapp.net", "Hello world!")
    assert link == "https://wa.me/15552223333?text=Hello%20world%21"


def test_build_whatsapp_link_returns_none_for_invalid_chat():
    assert build_whatsapp_link("not-a-phone", "hello") is None


def test_format_assistant_delivery_with_link():
    text = format_assistant_delivery(_msg("15552223333@s.whatsapp.net", "hello"))
    assert "Scheduled message ready" in text
    assert "https://wa.me/15552223333?text=hello" in text


def test_format_assistant_delivery_without_link():
    text = format_assistant_delivery(_msg("group:abc", "hello"))
    assert "Send link unavailable" in text
