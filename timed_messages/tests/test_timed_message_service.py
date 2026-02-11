from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from timed_messages.core.models import MessageStatus
from timed_messages.core.service import TimedMessageService


def test_schedule_message_validates_future_and_timezone(fake_repo, fixed_now, monkeypatch):
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)
    with pytest.raises(ValueError, match="timezone-aware"):
        service.schedule_message(
            chat_id="123",
            text="hi",
            send_at=datetime(2024, 1, 1, 12, 0),
            idempotency_key="key-1",
            source="test",
        )

    with pytest.raises(ValueError, match="future"):
        service.schedule_message(
            chat_id="123",
            text="hi",
            send_at=fixed_now,
            idempotency_key="key-2",
            source="test",
        )


def test_schedule_message_enforces_assistant_mode_sender(fake_repo, fixed_now, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)
    with pytest.raises(ValueError, match="from_chat_id"):
        service.schedule_message(
            chat_id="123",
            text="hello",
            send_at=fixed_now + timedelta(hours=1),
            idempotency_key="key-3",
            source="test",
        )


def test_schedule_message_idempotent(fake_repo, fixed_now):
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)
    send_at = fixed_now + timedelta(hours=1)
    first = service.schedule_message(
        chat_id="123",
        text="hello",
        send_at=send_at,
        idempotency_key="dup",
        source="test",
    )
    second = service.schedule_message(
        chat_id="123",
        text="hello",
        send_at=send_at,
        idempotency_key="dup",
        source="test",
    )
    assert first.id == second.id


def test_send_message_if_due_sends_and_marks_sent(fake_repo, fake_transport, fixed_now):
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)
    msg = service.schedule_message(
        chat_id="15551234567@s.whatsapp.net",
        text="ping",
        send_at=fixed_now + timedelta(minutes=1),
        idempotency_key="send-1",
        source="test",
    )

    service.send_message_if_due(msg.id, fake_transport, quoted_message_id=None)
    assert not fake_transport.sent

    later = fixed_now + timedelta(minutes=2)
    service.clock = lambda: later
    service.send_message_if_due(msg.id, fake_transport, quoted_message_id=None)

    assert fake_transport.sent[0]["chat_id"] == "15551234567@s.whatsapp.net"
    assert fake_repo.get_by_id(msg.id).status == MessageStatus.SENT


def test_send_message_if_due_assistant_mode(fake_repo, fake_transport, fixed_now, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)
    msg = service.schedule_message(
        chat_id="15551234567@s.whatsapp.net",
        from_chat_id="19998887777@s.whatsapp.net",
        text="hello there",
        send_at=fixed_now + timedelta(minutes=1),
        idempotency_key="send-2",
        source="test",
    )
    service.clock = lambda: fixed_now + timedelta(minutes=2)
    service.send_message_if_due(msg.id, fake_transport, quoted_message_id=None)

    assert fake_transport.sent
    assert fake_transport.sent[0]["chat_id"] == "19998887777@s.whatsapp.net"
    assert "Scheduled message ready" in fake_transport.sent[0]["text"]


def test_cancel_message_behaves_by_status(fake_repo, fixed_now):
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)
    msg = service.schedule_message(
        chat_id="123",
        text="ping",
        send_at=fixed_now + timedelta(hours=1),
        idempotency_key="cancel-1",
        source="test",
    )
    service.cancel_message(msg.id)
    assert fake_repo.get_by_id(msg.id).status == MessageStatus.CANCELLED

    fake_repo.mark_sent(msg.id, sent_at=fixed_now + timedelta(hours=2))
    with pytest.raises(ValueError, match="Cannot cancel"):
        service.cancel_message(msg.id)


def test_validate_assistant_schedule_window(monkeypatch, fake_repo, fixed_now):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MAX_SCHEDULE_HOURS", "2")
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)

    service.validate_assistant_schedule_window(send_at=fixed_now + timedelta(hours=1))
    with pytest.raises(ValueError, match="Free version limit"):
        service.validate_assistant_schedule_window(send_at=fixed_now + timedelta(hours=3))
