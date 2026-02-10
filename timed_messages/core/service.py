from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
import re
import secrets
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID
from zoneinfo import ZoneInfo
from urllib.parse import quote

from .models import ScheduledMessage, MessageStatus
from .repository import ScheduledMessageRepository
from timed_messages.runtime_config import runtime_config
from shared.runtime_config import assistant_mode_enabled

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..transport.whatsapp import WhatsAppTransport


class TimedMessageService:
    def __init__(self, repo: ScheduledMessageRepository, clock=None):
        self.repo = repo
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ---------- Public API ----------

    def schedule_message(
        self,
        *,
        chat_id: str,
        from_chat_id: str | None = None,
        text: str,
        send_at: datetime,
        idempotency_key: str,
        source: str,
        reason: str | None = None,
    ) -> ScheduledMessage:
        now = self.clock()

        if send_at.tzinfo is None:
            raise ValueError("send_at must be timezone-aware (UTC)")

        if send_at <= now:
            raise ValueError("send_at must be in the future")

        if assistant_mode_enabled() and not from_chat_id:
            raise ValueError("from_chat_id required in assistant mode")

        # Idempotency check
        existing = self.repo.find_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        msg = ScheduledMessage(
            id=uuid4(),
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            text=text,
            send_at=send_at,
            status=MessageStatus.SCHEDULED,
            locked_at=None,
            sent_at=None,
            attempt_count=0,
            last_error=None,
            idempotency_key=idempotency_key,
            source=source,
            reason=reason,
            created_at=now,
            updated_at=now,
        )

        self.repo.create(msg)
        return msg

    def validate_assistant_schedule_window(
        self,
        *,
        send_at: datetime,
        now: datetime | None = None,
    ) -> None:
        if not assistant_mode_enabled():
            return

        current = now or self.clock()
        max_window = self._assistant_schedule_window()
        if send_at - current <= max_window:
            return

        hours = int(max_window.total_seconds() // 3600)
        raise ValueError(
            "Free version limit: I can only schedule within "
            f"{hours} hours in assistant mode. "
            "Long-range scheduling uses paid Meta messaging, and I'm working for free :/"
        )

    def _assistant_schedule_window(self) -> timedelta:
        value = os.getenv("WHATSAPP_ASSISTANT_MAX_SCHEDULE_HOURS", "24").strip()
        try:
            hours = int(value)
        except ValueError:
            hours = 24
        if hours <= 0:
            hours = 24
        return timedelta(hours=hours)

    def cancel_message(self, msg_id: UUID) -> None:
        msg = self.repo.get_by_id(msg_id)
        if not msg:
            return

        if msg.status == MessageStatus.SENT:
            raise ValueError("Cannot cancel a sent message")

        if msg.status == MessageStatus.CANCELLED:
            return

        self.repo.cancel(msg_id)

    def get_message(self, msg_id: UUID) -> ScheduledMessage | None:
        return self.repo.get_by_id(msg_id)

    def find_by_id_prefix(self, prefix: str) -> ScheduledMessage | None:
        matches = self.repo.find_by_id_prefix(prefix, limit=2)
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError("cancel id is ambiguous; please paste the full ID")
        return matches[0]

    # ---------- Worker-facing API ----------

    def list_due_messages(self, limit: int = 10) -> list[ScheduledMessage]:
        now = self.clock()
        return self.repo.list_upcoming(now=now, limit=limit)

    def list_scheduled_messages(self, limit: int = 10) -> list[ScheduledMessage]:
        return self.repo.list_scheduled(limit=limit)

    def list_scheduled_messages_for_sender(
        self,
        *,
        sender_id: str,
        limit: int = 10,
    ) -> list[ScheduledMessage]:
        normalized_sender = self._normalize_sender_id(sender_id)
        if not normalized_sender:
            return []
        return self.repo.list_scheduled_for_sender(
            normalized_sender_id=normalized_sender,
            limit=limit,
        )

    def find_by_id_prefix_for_sender(
        self,
        *,
        prefix: str,
        sender_id: str,
    ) -> ScheduledMessage | None:
        normalized_sender = self._normalize_sender_id(sender_id)
        if not normalized_sender:
            return None
        matches = self.repo.find_by_id_prefix_for_sender(
            prefix=prefix,
            normalized_sender_id=normalized_sender,
            limit=2,
        )
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError("cancel id is ambiguous; please paste the full ID")
        return matches[0]

    def set_confirmation_message_id(
        self,
        *,
        msg_id: UUID,
        confirmation_message_id: str,
    ) -> None:
        if not confirmation_message_id:
            return
        self.repo.set_confirmation_message_id(msg_id, confirmation_message_id)

    def find_scheduled_by_confirmation_message_id_for_sender(
        self,
        *,
        confirmation_message_id: str,
        sender_id: str,
    ) -> ScheduledMessage | None:
        normalized_sender = self._normalize_sender_id(sender_id)
        if not normalized_sender or not confirmation_message_id:
            return None
        return self.repo.find_scheduled_by_confirmation_message_id_for_sender(
            confirmation_message_id=confirmation_message_id,
            normalized_sender_id=normalized_sender,
        )

    def send_message_if_due(
        self,
        msg_id: UUID,
        transport: WhatsAppTransport,
        quoted_message_id: Optional[UUID],
    ) -> None:
        """
        send_func(chat_id: str, text: str, message_id: UUID) -> None
        """
        now = self.clock()
        msg = self.repo.get_by_id(msg_id)

        if not msg:
            return

        if msg.status in {
            MessageStatus.CANCELLED,
            MessageStatus.SENT,
            MessageStatus.FAILED,
        }:
            return

        if msg.send_at > now:
            return

        # Atomic lock
        locked = self.repo.lock_for_sending(msg_id, now)
        if not locked:
            return

        try:
            if assistant_mode_enabled():
                if not msg.from_chat_id:
                    raise ValueError("from_chat_id is required in assistant mode")
                delivery_text = self._format_assistant_delivery(msg)
                transport.send_message(
                    chat_id=msg.from_chat_id,
                    text=delivery_text,
                    message_id=msg.id,
                    quoted_message_id=quoted_message_id
                )
            else:
                transport.send_message(
                    chat_id=msg.chat_id,
                    text=msg.text,
                    message_id=msg.id,
                    quoted_message_id=quoted_message_id
                )
            self.repo.mark_sent(msg_id, sent_at=now)

        except Exception as e:
            self.repo.mark_failed(msg_id, error=str(e))
            raise

    def _format_assistant_delivery(self, msg: ScheduledMessage) -> str:
        link = self._build_whatsapp_link(msg.chat_id, msg.text)
        to_display = self._display_chat_id(msg.chat_id)
        preview = (msg.text or "").strip().replace("\n", " ")
        if len(preview) > 160:
            preview = f"{preview[:157]}..."
        if link:
            return (
                "⏰ Scheduled message ready\n"
                f"To: {to_display}\n"
                f"Text: {preview}\n"
                f"Send: {link}"
            )
        return (
            "⏰ Scheduled message ready\n"
            f"To: {to_display}\n"
            f"Text: {preview}\n"
            "Send link unavailable for this recipient."
        )

    def _build_whatsapp_link(self, chat_id: str, text: str) -> str | None:
        digits = re.sub(r"\D", "", chat_id or "")
        if not digits:
            return None
        encoded = quote(text or "", safe="")
        return f"https://wa.me/{digits}?text={encoded}"

    def _display_chat_id(self, value: str) -> str:
        if "@" in value:
            return value.split("@", 1)[0]
        return value

    def _normalize_sender_id(self, sender_id: str) -> str:
        digits = re.sub(r"\D", "", sender_id or "")
        return digits if digits else (sender_id or "").strip()


class WhatsAppEventService:
    _flow_ttl = timedelta(minutes=30)
    _flows: dict[tuple[str, str], dict[str, object]] = {}
    _auth_ttl = timedelta(minutes=30)
    _auth_codes: dict[str, dict[str, object]] = {}

    def __init__(self, timed_service: TimedMessageService, transport: WhatsAppTransport):
        self.timed_service = timed_service
        self.transport = transport

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
        if normalized_text.startswith("!whoami"):
            return self._handle_whoami(
                chat_id=chat_id,
                sender_id=sender_id,
                message_id=message_id,
                text=text,
            )
        if normalized_text.startswith("!auth"):
            return self._handle_assistant_auth(
                chat_id=chat_id,
                sender_id=sender_id,
                message_id=message_id,
                text=text,
                is_group=is_group,
            )
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

        if assistant_mode and not self._is_sender_approved(sender_id):
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

        if command.lower() in ("instructions", "help", "commands", "hi"):
            self._send_reply(chat_id, self._build_instructions_reply(), message_id)
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
        flow = self._flows.get(key)
        if not flow:
            return None
        updated_at = flow.get("updated_at")
        if isinstance(updated_at, datetime) and timestamp - updated_at > self._flow_ttl:
            self._flows.pop(key, None)
            return None
        return flow

    def _handle_whoami(
        self,
        *,
        chat_id: str,
        sender_id: str,
        message_id: str,
        text: str,
    ) -> tuple[bool, Optional[str]]:
        admin_id = runtime_config.admin_sender_id()
        if admin_id:
            self._send_reply(chat_id, "✅ Admin already set.", message_id)
            return True, None

        parts = text.strip().split(None, 1)
        code = parts[1].strip() if len(parts) > 1 else ""
        if code != runtime_config.admin_setup_code():
            self._send_reply(chat_id, "❌ Invalid setup code.", message_id)
            return False, "invalid_setup_code"

        runtime_config.set_admin_sender_id(sender_id)
        self._send_reply(chat_id, f"✅ Admin set to {sender_id}.", message_id)
        return True, None

    def _handle_assistant_auth(
        self,
        *,
        chat_id: str,
        sender_id: str,
        message_id: str,
        text: str,
        is_group: bool,
    ) -> tuple[bool, Optional[str]]:
        if is_group:
            self._send_reply(chat_id, "❌ Please DM me to authenticate.", message_id)
            return False, "auth_in_group"

        normalized = self._normalize_sender_id(sender_id)
        if runtime_config.is_sender_approved(sender_id):
            self._send_reply(chat_id, "✅ Already approved.", message_id)
            return True, None

        parts = text.strip().split(None, 1)
        if len(parts) == 1:
            code = self._generate_auth_code()
            self._set_pending_auth(sender_id, code, self._now())
            logger.warning("Assistant auth code for %s: %s", normalized, code)
            self._send_reply(
                chat_id,
                "✅ Auth code generated. Ask the admin for it, then reply: !auth <code>.",
                message_id,
            )
            return True, None

        pending = self._get_pending_auth(sender_id, self._now())
        if not pending:
            self._send_reply(chat_id, "❌ No pending auth request. Send !auth to generate a new code.", message_id)
            return False, "auth_not_requested"

        code = parts[1].strip()
        if code != pending.get("code"):
            self._send_reply(chat_id, "❌ Invalid auth code. Send !auth to generate a new code.", message_id)
            return False, "invalid_auth_code"

        runtime_config.add_approved_number(normalized)
        self._clear_pending_auth(sender_id)
        self._send_reply(
            chat_id,
            f"✅ Approved: {normalized}.\n\n{self._build_instructions_reply(include_welcome=False)}",
            message_id,
        )
        return True, None

    def _handle_setup_command(
        self,
        *,
        chat_id: str,
        sender_id: str,
        message_id: str,
        command: str,
    ) -> tuple[bool, Optional[str]]:
        admin_id = runtime_config.admin_sender_id()
        if not admin_id:
            self._send_reply(
                chat_id,
                "❌ Admin sender ID not configured.",
                message_id,
            )
            return False, "admin_not_configured"

        if sender_id != admin_id:
            self._send_reply(chat_id, "❌ Unauthorized.", message_id)
            return False, "unauthorized_admin"

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

    def _is_sender_approved(self, sender_id: str) -> bool:
        return runtime_config.is_sender_approved(sender_id)

    def _normalize_sender_id(self, sender_id: str) -> str:
        return runtime_config.normalize_sender_id(sender_id)

    def _generate_auth_code(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def _get_pending_auth(self, sender_id: str, now: datetime) -> Optional[dict[str, object]]:
        key = self._normalize_sender_id(sender_id)
        entry = self._auth_codes.get(key)
        if not entry:
            return None
        updated_at = entry.get("updated_at")
        if isinstance(updated_at, datetime) and now - updated_at > self._auth_ttl:
            self._auth_codes.pop(key, None)
            return None
        return entry

    def _set_pending_auth(self, sender_id: str, code: str, now: datetime) -> None:
        key = self._normalize_sender_id(sender_id)
        self._auth_codes[key] = {"code": code, "updated_at": now}

    def _clear_pending_auth(self, sender_id: str) -> None:
        key = self._normalize_sender_id(sender_id)
        self._auth_codes.pop(key, None)

    def _start_flow(
        self,
        chat_id: str,
        sender_id: str,
        message_id: str,
        timestamp: datetime,
    ) -> None:
        self._flows[(chat_id, sender_id)] = {
            "step": "to",
            "request_id": message_id,
            "sender_id": sender_id,
            "updated_at": timestamp,
        }

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
            self._flows.pop((chat_id, str(flow.get("sender_id"))), None)
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
            self._flows.pop((chat_id, str(flow.get("sender_id"))), None)
            return True, None

        return False, "not_actionable"

    def _parse_datetime(self, value: str, tz_name: str | None) -> datetime:
        value = value.strip()
        lowered = value.lower()
        tz = self._load_timezone(tz_name)
        now = self._now().astimezone(tz)

        # Fast path: HH:MM means the next occurrence in the configured timezone.
        if re.fullmatch(r"\d{1,2}:\d{2}", value):
            try:
                time_part = datetime.strptime(value, "%H:%M").time()
            except ValueError as exc:
                raise ValueError("invalid time (use HH:MM)") from exc
            send_at = datetime.combine(now.date(), time_part, tzinfo=tz)
            if send_at <= now:
                send_at = send_at + timedelta(days=1)
            return send_at

        if lowered.startswith("today") or lowered.startswith("tomorrow"):
            parts = lowered.split()
            if len(parts) < 2:
                raise ValueError("time required (use 'today HH:MM' or 'tomorrow HH:MM')")
            try:
                time_part = datetime.strptime(parts[1], "%H:%M").time()
            except ValueError as exc:
                raise ValueError("invalid time (use HH:MM)") from exc
            base_date = now.date()
            if parts[0] == "tomorrow":
                base_date = base_date + timedelta(days=1)
            send_at = datetime.combine(base_date, time_part, tzinfo=tz)
            return send_at

        try:
            send_at = datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError("invalid 'at' format (use YYYY-MM-DD HH:MM)") from exc
        return send_at.replace(tzinfo=tz)

    def _now(self) -> datetime:
        return self.timed_service.clock()

    def _format_when_prompt(self) -> str:
        tz_name = os.getenv("DEFAULT_TIMEZONE") or "UTC"
        return (
            "*When?*\nUse YYYY-MM-DD HH:MM\n"
            "Or use HH:MM / 'today HH:MM' / 'tomorrow HH:MM'.\n"
            "For example: today 18:30\n"
            f"(Current time zone: {tz_name})"
        )

    def _normalize_recipient(
        self,
        value: str,
        contact_name: Optional[str],
        contact_phone: Optional[str],
    ) -> Optional[str]:
        value = value.strip()
        if value and "@" in value:
            return value

        if value:
            digits = re.sub(r"\D", "", value)
            if len(digits) >= 8:
                return f"{digits}@s.whatsapp.net"

        if contact_phone:
            digits = re.sub(r"\D", "", contact_phone)
            if len(digits) >= 8:
                return f"{digits}@s.whatsapp.net"

        return None

    def _normalize_contact_phone(
        self,
        contact_phone: Optional[str | list[str]],
    ) -> tuple[Optional[str], Optional[str]]:
        if isinstance(contact_phone, list):
            normalized = []
            for value in contact_phone:
                digits = re.sub(r"\D", "", str(value or ""))
                if len(digits) >= 8 and digits not in normalized:
                    normalized.append(digits)
            if len(normalized) > 1:
                return None, "multiple_numbers"
            if len(normalized) == 1:
                return normalized[0], None
            return None, None

        if not contact_phone:
            return None, None
        digits = re.sub(r"\D", "", str(contact_phone))
        if len(digits) >= 8:
            return digits, None
        return None, None

    def _load_timezone(self, tz_name: str | None) -> ZoneInfo:
        if not tz_name:
            raise ValueError("timezone required; add 'tz:' or set DEFAULT_TIMEZONE")
        try:
            return ZoneInfo(tz_name)
        except Exception as exc:
            raise ValueError(f"invalid timezone '{tz_name}'") from exc

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
        if not text:
            return None
        match = re.search(r"\b([0-9a-fA-F]{12})\b", text)
        return match.group(1) if match else None

    def _format_schedule_reply(self, *, scheduled_id: str, to_value: str, send_at: datetime) -> str:
        display_at = self._format_datetime(send_at)
        short_id = scheduled_id.replace("-", "")[:12]
        return (
            "✅ Scheduled\n"
            f"ID: {short_id}\n"
            f"To: {self._display_recipient(to_value)}\n"
            f"At: {display_at}"
        )

    def _format_list_reply(self, messages: list[ScheduledMessage]) -> str:
        if not messages:
            return "✅ No scheduled messages"

        lines = ["✅ Scheduled messages"]
        for msg in messages:
            when = self._format_datetime(msg.send_at)
            preview = msg.text.strip().replace("\n", " ")
            if len(preview) > 40:
                preview = f"{preview[:37]}..."
            lines.append(f"- {msg.id.hex[:12]} | {when} | {preview}")
        return "\n".join(lines)

    def _build_instructions_reply(self, *, include_welcome: bool = False) -> str:
        lines: list[str] = []
        if include_welcome:
            lines.append("welcome to the personal assistant bot, here are the commands you can run:")
        else:
            lines.append("Here are the commands you can run:")

        instructions = runtime_config.instructions()
        if instructions:
            for instruction in instructions.values():
                lines.append(f"- {instruction}")
        else:
            lines.append(
                "- Timed Messages: use add to schedule, list to view pending messages, and cancel by replying 'cancel' to a scheduled confirmation."
            )
        return "\n".join(lines)

    def _send_reply(self, chat_id: str, text: str, quoted_message_id: str | None) -> str | None:
        try:
            return self.transport.send_message(
                chat_id=chat_id,
                text=text,
                quoted_message_id=quoted_message_id,
            )
        except Exception:
            return None

    def _format_datetime(self, value: datetime) -> str:
        tz_name = os.getenv("DEFAULT_TIMEZONE")
        if tz_name:
            try:
                value = value.astimezone(self._load_timezone(tz_name))
            except Exception:
                pass
        return value.strftime("%Y-%m-%d %H:%M")

    def _display_recipient(self, value: str) -> str:
        if "@" in value:
            return value.split("@", 1)[0]
        return value
