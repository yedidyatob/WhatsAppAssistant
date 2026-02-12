from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from timed_messages.core.models import MessageStatus
from timed_messages.core.service import TimedMessageService
from timed_messages.core.whatsapp_event_service import WhatsAppEventService
from timed_messages.runtime_config import runtime_config



@pytest.fixture
def runtime_state(monkeypatch):
    state = {
        "admin_sender_id": "",
        "approved_numbers": set(),
        "group_id": "",
        "admin_setup_code": "123456",
    }

    monkeypatch.setattr(runtime_config, "admin_sender_id", lambda: state["admin_sender_id"])
    monkeypatch.setattr(runtime_config, "admin_setup_code", lambda: state["admin_setup_code"])
    monkeypatch.setattr(runtime_config, "set_admin_sender_id", lambda value: state.update({"admin_sender_id": value}))
    monkeypatch.setattr(runtime_config, "approved_numbers", lambda: list(state["approved_numbers"]))
    monkeypatch.setattr(runtime_config, "add_approved_number", lambda value: state["approved_numbers"].add(value))
    monkeypatch.setattr(runtime_config, "remove_approved_number", lambda value: state["approved_numbers"].discard(value))
    monkeypatch.setattr(runtime_config, "normalize_sender_id", lambda value: "".join(ch for ch in value if ch.isdigit()))
    monkeypatch.setattr(runtime_config, "is_sender_approved", lambda value: "".join(ch for ch in value if ch.isdigit()) in state["approved_numbers"])
    monkeypatch.setattr(runtime_config, "scheduling_group", lambda: state["group_id"])
    monkeypatch.setattr(runtime_config, "set_scheduling_group", lambda value: state.update({"group_id": value}))
    monkeypatch.setattr(runtime_config, "clear_scheduling_group", lambda: state.update({"group_id": ""}))

    return state


def _service_pair(fake_repo, fake_transport, fixed_now):
    service = TimedMessageService(fake_repo, clock=lambda: fixed_now)
    event_service = WhatsAppEventService(service, fake_transport)
    return service, event_service


def _handle(event_service, fixed_now, **overrides):
    payload = {
        "message_id": "m1",
        "chat_id": "group-1",
        "sender_id": "15551234567",
        "text": "",
        "quoted_text": None,
        "quoted_message_id": None,
        "contact_name": None,
        "contact_phone": None,
        "timestamp": fixed_now,
        "is_group": True,
        "raw": None,
    }
    payload.update(overrides)
    return event_service.handle_inbound_event(**payload)


def test_assistant_mode_blocks_unauthorized_sender(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, chat_id="dm-1", is_group=False, text="add")

    assert handled is False
    assert reason == "unauthorized_sender"
    assert "Unauthorized" in fake_transport.sent[-1]["text"]


def test_non_assistant_rejects_wrong_group(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "allowed-group"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, chat_id="group-1", text="add")

    assert handled is False
    assert reason == "unauthorized_group"


def test_whoami_requires_valid_setup_code(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, text="!whoami 000000")

    assert handled is False
    assert reason == "invalid_setup_code"
    assert "Invalid setup code" in fake_transport.sent[-1]["text"]


def test_whoami_sets_admin_once(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, text="!whoami 123456")

    assert handled is True
    assert reason is None
    assert runtime_state["admin_sender_id"] == "15551234567"

    handled, reason = _handle(event_service, fixed_now, text="!whoami 123456")
    assert handled is True
    assert reason is None
    assert "already set" in fake_transport.sent[-1]["text"].lower()


def test_auth_happy_path_and_edge_cases(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    monkeypatch.setattr(event_service, "_generate_auth_code", lambda: "654321")

    handled, reason = _handle(event_service, fixed_now, chat_id="dm-1", is_group=False, text="!auth")
    assert handled is True and reason is None
    assert "Auth code generated" in fake_transport.sent[-1]["text"]

    handled, reason = _handle(event_service, fixed_now, chat_id="dm-1", is_group=False, text="!auth 111111")
    assert handled is False and reason == "invalid_auth_code"

    handled, reason = _handle(event_service, fixed_now, chat_id="dm-1", is_group=False, text="!auth 654321")
    assert handled is True and reason is None
    assert "15551234567" in runtime_state["approved_numbers"]

    handled, reason = _handle(event_service, fixed_now, chat_id="dm-1", is_group=False, text="!auth 654321")
    assert handled is True and reason is None
    assert "Already approved" in fake_transport.sent[-1]["text"]


def test_auth_rejected_in_group(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, is_group=True, text="!auth")

    assert handled is False
    assert reason == "auth_in_group"


def test_auth_notifies_admin_with_requester_details(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")
    runtime_state["admin_sender_id"] = "15559990000"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    monkeypatch.setattr(event_service, "_generate_auth_code", lambda: "654321")

    handled, reason = _handle(
        event_service,
        fixed_now,
        chat_id="dm-1",
        is_group=False,
        text="!auth",
        contact_name="Alice",
        contact_phone="+972547792585",
    )

    assert handled is True and reason is None
    assert len(fake_transport.sent) == 2
    assert fake_transport.sent[0]["chat_id"] == "15559990000"
    assert "Code: 654321" in fake_transport.sent[0]["text"]
    assert "Name: Alice" in fake_transport.sent[0]["text"]
    assert "Phone: +972547792585" in fake_transport.sent[0]["text"]


def test_auth_admin_notification_falls_back_to_raw_contact(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")
    runtime_state["admin_sender_id"] = "15559990000"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    monkeypatch.setattr(event_service, "_generate_auth_code", lambda: "654321")

    handled, reason = _handle(
        event_service,
        fixed_now,
        chat_id="dm-1",
        sender_id="972547792585@s.whatsapp.net",
        is_group=False,
        text="!auth",
        raw={"contacts": [{"wa_id": "972547792585", "profile": {"name": "Bob"}}]},
    )

    assert handled is True and reason is None
    assert "Name: Bob" in fake_transport.sent[0]["text"]
    assert "Phone: 972547792585" in fake_transport.sent[0]["text"]


def test_setup_commands_require_admin_when_not_assistant(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, text="!setup timed messages")
    assert handled is False
    assert reason == "admin_not_configured"

    runtime_state["admin_sender_id"] = "15559990000"
    handled, reason = _handle(event_service, fixed_now, text="!setup timed messages")
    assert handled is False
    assert reason == "unauthorized_admin"

    handled, reason = _handle(
        event_service,
        fixed_now,
        text="!setup timed messages",
        sender_id="15559990000",
    )
    assert handled is True and reason is None
    assert runtime_state["group_id"] == "group-1"

    handled, reason = _handle(
        event_service,
        fixed_now,
        text="!stop timed messages",
        sender_id="15559990000",
    )
    assert handled is True and reason is None
    assert runtime_state["group_id"] == ""


def test_setup_commands_in_assistant_mode(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")
    runtime_state["approved_numbers"].add("15551234567")

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, chat_id="dm-1", is_group=False, text="!setup timed messages")

    assert handled is True
    assert reason is None
    assert "not needed in assistant mode" in fake_transport.sent[-1]["text"].lower()


def test_help_instructions_and_not_actionable(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, text="instructions")
    assert handled is True and reason is None
    assert "Options:" in fake_transport.sent[-1]["text"]

    handled, reason = _handle(event_service, fixed_now, text="just chatting")
    assert handled is False and reason == "not_actionable"


def test_list_and_cancel_paths(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    service, event_service = _service_pair(fake_repo, fake_transport, fixed_now)

    # list empty
    handled, reason = _handle(event_service, fixed_now, text="list")
    assert handled is True and reason is None
    assert "No scheduled messages" in fake_transport.sent[-1]["text"]

    # schedule one and list
    msg = service.schedule_message(
        chat_id="19998887777@s.whatsapp.net",
        from_chat_id="15551234567",
        text="hello",
        send_at=fixed_now + timedelta(hours=1),
        idempotency_key="key-list",
        source="test",
    )
    handled, reason = _handle(event_service, fixed_now, text="list")
    assert handled is True and reason is None
    assert msg.id.hex[:12] in fake_transport.sent[-1]["text"]

    # invalid cancel
    handled, reason = _handle(event_service, fixed_now, text="cancel")
    assert handled is False
    assert reason == "Invalid_cancel_id. Reply to an approval message with the word cancel."

    # valid cancel by prefix
    handled, reason = _handle(event_service, fixed_now, text=f"cancel {msg.id.hex[:12]}")
    assert handled is True and reason is None
    assert fake_repo.get_by_id(msg.id).status == MessageStatus.CANCELLED


def test_cancel_by_quoted_confirmation_message(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    service, event_service = _service_pair(fake_repo, fake_transport, fixed_now)

    msg = service.schedule_message(
        chat_id="19998887777@s.whatsapp.net",
        from_chat_id="15551234567",
        text="hello",
        send_at=fixed_now + timedelta(hours=1),
        idempotency_key="key-confirm",
        source="test",
    )
    service.set_confirmation_message_id(msg_id=msg.id, confirmation_message_id="confirm-1")

    handled, reason = _handle(
        event_service,
        fixed_now,
        text="cancel",
        quoted_message_id="confirm-1",
    )

    assert handled is True and reason is None
    assert fake_repo.get_by_id(msg.id).status == MessageStatus.CANCELLED


def test_cancel_ambiguous_prefix(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    service, event_service = _service_pair(fake_repo, fake_transport, fixed_now)

    a = service.schedule_message(
        chat_id="19998887777@s.whatsapp.net",
        from_chat_id="15551234567",
        text="a",
        send_at=fixed_now + timedelta(hours=1),
        idempotency_key=str(uuid4()),
        source="test",
    )
    b = service.schedule_message(
        chat_id="19998887777@s.whatsapp.net",
        from_chat_id="15551234567",
        text="b",
        send_at=fixed_now + timedelta(hours=2),
        idempotency_key=str(uuid4()),
        source="test",
    )

    # force an ambiguous prefix in the fake repo
    fake_repo.find_by_id_prefix_for_sender = lambda prefix, normalized_sender_id, limit=2: [a, b]

    handled, reason = _handle(event_service, fixed_now, text="cancel abcdef123456")

    assert handled is False
    assert reason == "cancel id is ambiguous; please paste the full ID"


def test_add_flow_valid_and_bad_replies(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    runtime_state["group_id"] = "group-1"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)

    handled, reason = _handle(event_service, fixed_now, text="add")
    assert handled is True and reason is None

    # bad 'to' reply
    handled, reason = _handle(event_service, fixed_now, text="invalid recipient")
    assert handled is True and reason is None
    assert "Please reply with a phone number" in fake_transport.sent[-1]["text"]

    # multiple numbers in contact should be rejected
    handled, reason = _handle(
        event_service,
        fixed_now,
        text="",
        contact_phone=["+1 555 111 2222", "+1 555 333 4444"],
    )
    assert handled is True
    assert reason == "multiple_recipient_numbers"

    # set valid recipient and continue
    handled, reason = _handle(event_service, fixed_now, text="15550001111")
    assert handled is True and reason is None

    # invalid when reply
    handled, reason = _handle(event_service, fixed_now, text="tomorrow")
    assert handled is True and reason is None
    assert "Invalid time" in fake_transport.sent[-1]["text"]

    # valid when reply
    handled, reason = _handle(event_service, fixed_now, text="today 13:00")
    assert handled is True and reason is None

    # empty text rejected
    handled, reason = _handle(event_service, fixed_now, text="   ")
    assert handled is True and reason is None
    assert "can't be empty" in fake_transport.sent[-1]["text"]

    # user can cancel during flow
    handled, reason = _handle(event_service, fixed_now, text="cancel")
    assert handled is True and reason is None
    assert "Canceled scheduling" in fake_transport.sent[-1]["text"]


def test_no_text_is_not_actionable_when_idle(fake_repo, fake_transport, fixed_now, runtime_state, monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    runtime_state["group_id"] = "group-1"

    _, event_service = _service_pair(fake_repo, fake_transport, fixed_now)
    handled, reason = _handle(event_service, fixed_now, text="")

    assert handled is False
    assert reason == "no_text"
