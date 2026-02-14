from datetime import datetime, timezone

from auth_service.app import AuthEventService, WhatsAppInboundEvent
from shared.auth_runtime_config import runtime_config


def _event(**overrides):
    payload = {
        "message_id": "m1",
        "timestamp": int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()),
        "chat_id": "dm-1",
        "sender_id": "15551234567@s.whatsapp.net",
        "is_group": False,
        "text": "",
        "quoted_text": None,
        "quoted_message_id": None,
        "contact_name": None,
        "contact_phone": None,
        "raw": None,
    }
    payload.update(overrides)
    return WhatsAppInboundEvent(**payload)


def test_auth_service_ignores_non_auth_commands(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "false")
    service = AuthEventService()
    handled, reason = service.handle_inbound_event(_event(text="add"))
    assert handled is False
    assert reason == "auth_command_only"


def test_auth_service_prompts_unauthorized_sender_in_assistant_mode(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ASSISTANT_MODE", "true")
    sent = []

    monkeypatch.setattr(runtime_config, "is_sender_approved", lambda value: False)

    service = AuthEventService()
    monkeypatch.setattr(service, "_send_reply", lambda chat_id, text, quoted: sent.append(text))
    service.auth_service._send_reply = service._send_reply

    handled, reason = service.handle_inbound_event(_event(text="hello there"))
    assert handled is False
    assert reason == "unauthorized_sender"
    assert "!auth" in sent[-1]


def test_whoami_flow(monkeypatch):
    state = {"admin_sender_id": "", "admin_setup_code": "123456", "approved_numbers": set()}
    sent = []

    monkeypatch.setattr(runtime_config, "admin_sender_id", lambda: state["admin_sender_id"])
    monkeypatch.setattr(runtime_config, "admin_setup_code", lambda: state["admin_setup_code"])
    monkeypatch.setattr(runtime_config, "set_admin_sender_id", lambda value: state.update({"admin_sender_id": value}))

    service = AuthEventService()
    monkeypatch.setattr(service, "_send_reply", lambda chat_id, text, quoted: sent.append(text))
    service.auth_service._send_reply = service._send_reply

    handled, reason = service.handle_inbound_event(_event(text="!whoami 000000"))
    assert handled is False and reason == "invalid_setup_code"

    handled, reason = service.handle_inbound_event(_event(text="!whoami 123456"))
    assert handled is True and reason is None
    assert state["admin_sender_id"] == "15551234567@s.whatsapp.net"


def test_auth_flow(monkeypatch):
    state = {"admin_sender_id": "", "admin_setup_code": "123456", "approved_numbers": set()}
    sent = []

    monkeypatch.setattr(runtime_config, "admin_sender_id", lambda: state["admin_sender_id"])
    monkeypatch.setattr(runtime_config, "is_sender_approved", lambda value: "15551234567" in state["approved_numbers"])
    monkeypatch.setattr(runtime_config, "normalize_sender_id", lambda value: "".join(ch for ch in value if ch.isdigit()))
    monkeypatch.setattr(runtime_config, "add_approved_number", lambda value: state["approved_numbers"].add(value))
    monkeypatch.setattr(
        runtime_config,
        "instructions",
        lambda: {
            "summarizer": "Summarizer: send any news article link to the assistant and get the summary back as a reply.",
            "timed_messages": "Timed Messages: use *add* to schedule, *list* to view pending messages, and cancel by replying *cancel* to a scheduled confirmation.",
        },
    )

    service = AuthEventService()
    monkeypatch.setattr(service, "_send_reply", lambda chat_id, text, quoted: sent.append(text))
    service.auth_service._send_reply = service._send_reply
    service.auth_code_generator.generate = lambda: "654321"

    handled, reason = service.handle_inbound_event(_event(text="!auth"))
    assert handled is True and reason is None
    assert "6-digit code" in sent[-1]

    handled, reason = service.handle_inbound_event(_event(text="111111"))
    assert handled is False and reason == "invalid_auth_code"

    handled, reason = service.handle_inbound_event(_event(text="654321"))
    assert handled is True and reason is None
    assert "15551234567" in state["approved_numbers"]
    assert any("welcome to the personal assistant bot" in message.lower() for message in sent)
    assert any("timed messages:" in message.lower() for message in sent)
