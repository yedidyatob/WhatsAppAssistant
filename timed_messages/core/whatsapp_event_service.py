from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from shared.auth_service import authorize_admin_command
from shared.runtime_config import assistant_mode_enabled
from timed_messages.runtime_config import runtime_config

from .flow_store import FlowStore, InMemoryFlowStore
from .models import ScheduledMessage
from .service import TimedMessageService
from .whatsapp_formatting import (
    format_list_reply,
    format_schedule_reply,
    format_when_prompt,
)
from .whatsapp_normalization import (
    extract_id_prefix,
    normalize_contact_phone,
    normalize_recipient,
)
from .whatsapp_time import parse_datetime

logger = logging.getLogger(__name__)



if TYPE_CHECKING:
    from ..transport.whatsapp import WhatsAppTransport

class WhatsAppEventService:
    _flow_ttl = timedelta(minutes=30)

    def __init__(
        self,
        timed_service: TimedMessageService,
        transport: WhatsAppTransport,
        *,
        flow_store: FlowStore | None = None
    ):
        self.timed_service = timed_service
        self.transport = transport
        self.flow_store = flow_store or InMemoryFlowStore(ttl=self._flow_ttl)

    def handle_inbound_event(
        self,
        *,
        message_id: str,
        chat_id: str,
        sender_id: str,
        text: Optional[str],
        quoted_text: Optional[str],
        quoted_message_id: Optional[str],
        contact_name: Optional[str],
        contact_phone: Optional[str | list[str]],
        timestamp: datetime,
        is_group: bool,
        raw: Optional[dict],
    ) -> tuple[bool, Optional[str]]:
        text = text.strip() if text else ""
        assistant_mode = assistant_mode_enabled()

        normalized_text = text.strip().lower()
        if normalized_text in {"!setup timed messages", "!stop timed messages"}:
            if assistant_mode:
                self._send_reply(
                    chat_id,
                    "ℹ️ Setup commands are not needed in assistant mode.",
                    message_id,
                )
                return True, None
            return self._handle_setup_command(
                chat_id=chat_id,
                sender_id=sender_id,
                message_id=message_id,
                command=normalized_text,
            )

        if assistant_mode and not runtime_config.is_sender_approved(sender_id):
            if not is_group:
                self._send_reply(
                    chat_id,
                    "❌ Unauthorized. Ask the admin for the auth code.",
                    message_id,
                )
            return False, "unauthorized_sender"

        if not assistant_mode:
            allowed_group = runtime_config.scheduling_group()
            if not allowed_group or chat_id != allowed_group:
                return False, "unauthorized_group"

        flow = self._get_active_flow(chat_id, sender_id, timestamp)
        if flow:
            return self._handle_flow_step(
                flow=flow,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                contact_name=contact_name,
                contact_phone=contact_phone,
                timestamp=timestamp,
            )

        if not text:
            return False, "no_text"

        command = text.split(None, 1)[0].lower()

        if command == "add":
            self._start_flow(chat_id, sender_id, message_id, timestamp)
            self._send_reply(
                chat_id,
                "*To Who?*\n(Phone number or contact)",
                message_id,
            )
            return True, None

        if command == "instructions":
            self._send_reply(
                chat_id,
                "Options:\n*add* (interactive scheduling),\n*list* (show scheduled),\n*cancel* (reply 'cancel' to a scheduled message).",
                message_id,
            )
            return True, None

        if command == "cancel":
            try:
                msg_id = self._resolve_cancel_id(
                    text=text,
                    quoted_text=quoted_text,
                    quoted_message_id=quoted_message_id,
                    sender_id=sender_id,
                )
            except ValueError as exc:
                self._send_reply(chat_id, f"❌ {exc}", message_id)
                return False, str(exc)
            if not msg_id:
                self._send_reply(chat_id, "❌ invalid cancel id", message_id)
                return False, "Invalid_cancel_id. Reply to an approval message with the word cancel."

            try:
                self.timed_service.cancel_message(msg_id)
            except ValueError as exc:
                self._send_reply(chat_id, f"❌ {exc}", message_id)
                return False, str(exc)

            self._send_reply(chat_id, f"✅ Cancelled\nID: {str(msg_id)}", message_id)
            return True, None

        if command == "list":
            scheduled = self.timed_service.list_scheduled_messages_for_sender(
                sender_id=sender_id,
                limit=5,
            )
            reply = self._format_list_reply(scheduled)
            self._send_reply(chat_id, reply, message_id)
            return True, None

        return False, "not_actionable"

    def _get_active_flow(
        self,
        chat_id: str,
        sender_id: str,
        timestamp: datetime,
    ) -> Optional[dict[str, object]]:
        key = (chat_id, sender_id)
        flow = self.flow_store.get(key, timestamp)
        if not flow:
            return None
        return flow

    def _handle_setup_command(
        self,
        *,
        chat_id: str,
        sender_id: str,
        message_id: str,
        command: str,
    ) -> tuple[bool, Optional[str]]:
        reason = authorize_admin_command(
            admin_sender_id=runtime_config.admin_sender_id(),
            sender_id=sender_id,
            send_reply=lambda text: self._send_reply(chat_id, text, message_id),
        )
        if reason:
            return False, reason

        if command == "!setup timed messages":
            runtime_config.set_scheduling_group(chat_id)
            self._send_reply(
                chat_id,
                "✅ Timed messages enabled for this group.",
                message_id,
            )
            return True, None

        runtime_config.clear_scheduling_group()
        self._send_reply(
            chat_id,
            "✅ Timed messages disabled for this group.",
            message_id,
        )
        return True, None

    def _start_flow(
        self,
        chat_id: str,
        sender_id: str,
        message_id: str,
        timestamp: datetime,
    ) -> None:
        self.flow_store.set((chat_id, sender_id), {
            "step": "to",
            "request_id": message_id,
            "sender_id": sender_id,
            "updated_at": timestamp,
        })

    def _handle_flow_step(
        self,
        *,
        flow: dict[str, object],
        chat_id: str,
        message_id: str,
        text: str,
        contact_name: Optional[str],
        contact_phone: Optional[str | list[str]],
        timestamp: datetime,
    ) -> tuple[bool, Optional[str]]:
        step = flow.get("step")
        flow["updated_at"] = timestamp
        if text.strip().lower() == "cancel":
            self.flow_store.clear((chat_id, str(flow.get("sender_id"))))
            self._send_reply(chat_id, "✅ Canceled scheduling.", message_id)
            return True, None

        if step == "to":
            normalized_contact_phone, contact_issue = self._normalize_contact_phone(contact_phone)
            if contact_issue == "multiple_numbers":
                self._send_reply(
                    chat_id,
                    "❌ Can't send to multiple numbers. Please share one contact with one phone number.",
                    message_id,
                )
                return True, "multiple_recipient_numbers"
            normalized = self._normalize_recipient(text, contact_name, normalized_contact_phone)
            if not normalized:
                self._send_reply(
                    chat_id,
                    "❌ Please reply with a phone number (digits, country code) or share a WhatsApp contact.",
                    message_id,
                )
                return True, None
            flow["to_chat_id"] = normalized
            flow["step"] = "when"
            self._send_reply(chat_id, self._format_when_prompt(), message_id)
            return True, None

        if step == "when":
            tz_name = os.getenv("DEFAULT_TIMEZONE")
            try:
                send_at = self._parse_datetime(text, tz_name)
            except ValueError:
                self._send_reply(chat_id, f"❌ Invalid time. {self._format_when_prompt()}", message_id)
                return True, None
            if send_at <= self._now():
                self._send_reply(chat_id, f"❌ Time must be in the future. {self._format_when_prompt()}", message_id)
                return True, None
            try:
                self.timed_service.validate_assistant_schedule_window(send_at=send_at)
            except ValueError as exc:
                self._send_reply(chat_id, f"❌ {exc}", message_id)
                return True, str(exc)
            flow["send_at"] = send_at
            flow["step"] = "text"
            self._send_reply(chat_id, "*What should I say?*", message_id)
            return True, None

        if step == "text":
            if not text.strip():
                self._send_reply(chat_id, "❌ Message text can't be empty. *What should I say?*", message_id)
                return True, None
            try:
                scheduled = self.timed_service.schedule_message(
                    chat_id=str(flow.get("to_chat_id")),
                    from_chat_id=str(flow.get("sender_id")),
                    text=text.strip(),
                    send_at=flow["send_at"],
                    idempotency_key=str(flow.get("request_id")),
                    source="whatsapp",
                    reason=f"whatsapp:{flow.get('request_id')}",
                )
            except ValueError as exc:
                if str(exc) == "send_at must be in the future":
                    flow["step"] = "when"
                    self._send_reply(chat_id, f"❌ Time must be in the future. {self._format_when_prompt()}", message_id)
                    return True, str(exc)
                self._send_reply(chat_id, f"❌ {exc}", message_id)
                return True, str(exc)
            reply = self._format_schedule_reply(
                scheduled_id=str(scheduled.id),
                to_value=str(flow.get("to_chat_id")),
                send_at=flow["send_at"],
            )
            confirmation_message_id = self._send_reply(chat_id, reply, message_id)
            if confirmation_message_id:
                self.timed_service.set_confirmation_message_id(
                    msg_id=scheduled.id,
                    confirmation_message_id=confirmation_message_id,
                )
            self.flow_store.clear((chat_id, str(flow.get("sender_id"))))
            return True, None

        return False, "not_actionable"

    def _parse_datetime(self, value: str, tz_name: str | None) -> datetime:
        return parse_datetime(value=value, tz_name=tz_name, now_utc=self._now())

    def _now(self) -> datetime:
        return self.timed_service.clock()

    def _format_when_prompt(self) -> str:
        tz_name = os.getenv("DEFAULT_TIMEZONE") or "UTC"
        return format_when_prompt(tz_name)

    def _normalize_recipient(
        self,
        value: str,
        contact_name: Optional[str],
        contact_phone: Optional[str],
    ) -> Optional[str]:
        return normalize_recipient(value=value, contact_phone=contact_phone)

    def _normalize_contact_phone(
        self,
        contact_phone: Optional[str | list[str]],
    ) -> tuple[Optional[str], Optional[str]]:
        return normalize_contact_phone(contact_phone)

    def _resolve_cancel_id(
        self,
        *,
        text: str,
        quoted_text: Optional[str],
        quoted_message_id: Optional[str],
        sender_id: str,
    ) -> UUID | None:
        prefix = self._extract_id_prefix(text) or self._extract_id_prefix(quoted_text)
        if prefix:
            match = self.timed_service.find_by_id_prefix_for_sender(
                prefix=prefix,
                sender_id=sender_id,
            )
            if not match:
                raise ValueError("could not find one of your scheduled messages with that ID")
            return match.id

        if quoted_message_id:
            match = self.timed_service.find_scheduled_by_confirmation_message_id_for_sender(
                confirmation_message_id=quoted_message_id,
                sender_id=sender_id,
            )
            if match:
                return match.id

        return None

    def _extract_id_prefix(self, text: Optional[str]) -> Optional[str]:
        return extract_id_prefix(text)

    def _format_schedule_reply(self, *, scheduled_id: str, to_value: str, send_at: datetime) -> str:
        return format_schedule_reply(
            scheduled_id=scheduled_id,
            to_value=to_value,
            send_at=send_at,
            tz_name=os.getenv("DEFAULT_TIMEZONE"),
        )

    def _format_list_reply(self, messages: list[ScheduledMessage]) -> str:
        return format_list_reply(messages, tz_name=os.getenv("DEFAULT_TIMEZONE"))

    def _send_reply(self, chat_id: str, text: str, quoted_message_id: str | None) -> str | None:
        try:
            return self.transport.send_message(
                chat_id=chat_id,
                text=text,
                quoted_message_id=quoted_message_id,
            )
        except Exception:
            return None
