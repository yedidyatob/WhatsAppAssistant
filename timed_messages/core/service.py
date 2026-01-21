from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
import re
from typing import Optional, TYPE_CHECKING
from uuid import uuid4, UUID
from zoneinfo import ZoneInfo

from .models import ScheduledMessage, MessageStatus
from .repository import ScheduledMessageRepository
from timed_messages.runtime_config import runtime_config

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

        # Idempotency check
        existing = self.repo.find_by_idempotency_key(idempotency_key)
        if existing:
            return existing

        msg = ScheduledMessage(
            id=uuid4(),
            chat_id=chat_id,
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

        if msg.status != MessageStatus.SCHEDULED:
            return

        if msg.send_at > now:
            return

        # Atomic lock
        locked = self.repo.lock_for_sending(msg_id, now)
        if not locked:
            return

        try:
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


class WhatsAppEventService:
    _flow_ttl = timedelta(minutes=30)
    _flows: dict[tuple[str, str], dict[str, object]] = {}

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
        contact_name: Optional[str],
        contact_phone: Optional[str],
        timestamp: datetime,
        is_group: bool,
        raw: Optional[dict],
    ) -> tuple[bool, Optional[str]]:
        text = text.strip() if text else ""

        normalized_text = text.strip().lower()
        if normalized_text.startswith("!whoami"):
            return self._handle_whoami(
                chat_id=chat_id,
                sender_id=sender_id,
                message_id=message_id,
                text=text,
            )
        if normalized_text in {"!setup timed messages", "!stop timed messages"}:
            return self._handle_setup_command(
                chat_id=chat_id,
                sender_id=sender_id,
                message_id=message_id,
                command=normalized_text,
            )

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

        if command == "schedule":
            try:
                parsed = self._parse_schedule(text)
            except ValueError as exc:
                return False, str(exc)

            try:
                scheduled = self.timed_service.schedule_message(
                    chat_id=parsed["to_chat_id"] or chat_id,
                    text=parsed["text"],
                    send_at=parsed["send_at"],
                    idempotency_key=message_id,
                    source="whatsapp",
                    reason=f"whatsapp:{message_id}",
                )
            except ValueError as exc:
                self._send_reply(chat_id, f"❌ {exc}", message_id)
                return False, str(exc)

            reply = self._format_schedule_reply(
                scheduled_id=str(scheduled.id),
                to_value=parsed.get("to_chat_id") or chat_id,
                send_at=parsed["send_at"],
            )
            self._send_reply(chat_id, reply, message_id)
            return True, None

        if command == "cancel":
            try:
                msg_id = self._resolve_cancel_id(text, quoted_text)
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
            scheduled = self.timed_service.list_scheduled_messages(limit=5)
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
        contact_phone: Optional[str],
        timestamp: datetime,
    ) -> tuple[bool, Optional[str]]:
        step = flow.get("step")
        flow["updated_at"] = timestamp
        if text.strip().lower() == "cancel":
            self._flows.pop((chat_id, str(flow.get("sender_id"))), None)
            self._send_reply(chat_id, "✅ Canceled scheduling.", message_id)
            return True, None

        if step == "to":
            normalized = self._normalize_recipient(text, contact_name, contact_phone)
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
            flow["send_at"] = send_at
            flow["step"] = "text"
            self._send_reply(chat_id, "What should I say?", message_id)
            return True, None

        if step == "text":
            if not text.strip():
                self._send_reply(chat_id, "❌ Message text can't be empty. What should I say?", message_id)
                return True, None
            try:
                scheduled = self.timed_service.schedule_message(
                    chat_id=str(flow.get("to_chat_id")),
                    text=text.strip(),
                    send_at=flow["send_at"],
                    idempotency_key=str(flow.get("request_id")),
                    source="whatsapp",
                    reason=f"whatsapp:{flow.get('request_id')}",
                )
            except ValueError as exc:
                self._send_reply(chat_id, f"❌ {exc}", message_id)
                return True, str(exc)
            reply = self._format_schedule_reply(
                scheduled_id=str(scheduled.id),
                to_value=str(flow.get("to_chat_id")),
                send_at=flow["send_at"],
            )
            self._send_reply(chat_id, reply, message_id)
            self._flows.pop((chat_id, str(flow.get("sender_id"))), None)
            return True, None

        return False, "not_actionable"

    def _parse_schedule(self, text: str) -> dict[str, object]:
        """
        Strict format:
        schedule
        to: <chat_id or @mention>
        at: 2026-01-20 16:00
        text: Reminder: pay rent
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines or lines[0].lower() != "schedule":
            raise ValueError("schedule must start with a 'schedule' line")

        fields: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                raise ValueError("schedule lines must be in 'key: value' format")
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if not value:
                raise ValueError(f"'{key}' value is required")
            fields[key] = value

        to_value = fields.get("to")
        at_value = fields.get("at")
        text_value = fields.get("text")
        tz_value = fields.get("tz") or os.getenv("DEFAULT_TIMEZONE")

        if not at_value or not text_value:
            raise ValueError("schedule requires 'at' and 'text' fields")

        send_at = self._parse_datetime(at_value, tz_value)
        return {"to_chat_id": to_value, "send_at": send_at, "text": text_value}

    def _parse_datetime(self, value: str, tz_name: str | None) -> datetime:
        value = value.strip()
        lowered = value.lower()
        if lowered.startswith("today") or lowered.startswith("tomorrow"):
            parts = lowered.split()
            if len(parts) < 2:
                raise ValueError("time required (use 'today HH:MM' or 'tomorrow HH:MM')")
            try:
                time_part = datetime.strptime(parts[1], "%H:%M").time()
            except ValueError as exc:
                raise ValueError("invalid time (use HH:MM)") from exc
            tz = self._load_timezone(tz_name)
            now = self._now().astimezone(tz)
            base_date = now.date()
            if parts[0] == "tomorrow":
                base_date = base_date + timedelta(days=1)
            send_at = datetime.combine(base_date, time_part, tzinfo=tz)
            return send_at

        try:
            send_at = datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError("invalid 'at' format (use YYYY-MM-DD HH:MM)") from exc
        return send_at.replace(tzinfo=self._load_timezone(tz_name))

    def _now(self) -> datetime:
        return self.timed_service.clock()

    def _format_when_prompt(self) -> str:
        tz_name = os.getenv("DEFAULT_TIMEZONE") or "UTC"
        return (
            "*When?*\nUse YYYY-MM-DD HH:MM\n"
            "Or use 'today' / 'tomorrow'.\n"
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

    def _load_timezone(self, tz_name: str | None) -> ZoneInfo:
        if not tz_name:
            raise ValueError("timezone required; add 'tz:' or set DEFAULT_TIMEZONE")
        try:
            return ZoneInfo(tz_name)
        except Exception as exc:
            raise ValueError(f"invalid timezone '{tz_name}'") from exc

    def _resolve_cancel_id(self, text: str, quoted_text: Optional[str]) -> UUID | None:
        prefix = self._extract_id_prefix(text) or self._extract_id_prefix(quoted_text)
        if not prefix:
            return None

        match = self.timed_service.find_by_id_prefix(prefix)
        if not match:
            raise ValueError("could not find a scheduled message with that ID")
        return match.id

    def _extract_id_prefix(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"\b([0-9a-fA-F]{12})\b", text)
        return match.group(1) if match else None

    def _format_schedule_reply(self, *, scheduled_id: str, to_value: str, send_at: datetime) -> str:
        # TODO: Resolve display names for @mentions instead of echoing raw to_value.
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

    def _send_reply(self, chat_id: str, text: str, quoted_message_id: str | None) -> None:
        try:
            self.transport.send_message(
                chat_id=chat_id,
                text=text,
                quoted_message_id=quoted_message_id,
            )
        except Exception:
            pass

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
