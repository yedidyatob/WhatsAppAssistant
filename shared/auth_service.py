from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def authorize_admin_command(
    *,
    admin_sender_id: str,
    sender_id: str,
    send_reply: Callable[[str], None],
) -> Optional[str]:
    if not admin_sender_id:
        send_reply("❌ Admin sender ID not configured.")
        return "admin_not_configured"

    if sender_id != admin_sender_id:
        send_reply("❌ Unauthorized.")
        return "unauthorized_admin"

    return None


@dataclass(frozen=True)
class AuthCommandContext:
    chat_id: str
    sender_id: str
    message_id: str
    text: str


@dataclass(frozen=True)
class AssistantAuthContext(AuthCommandContext):
    is_group: bool
    contact_name: Optional[str]
    contact_phone: Optional[str | list[str]]
    raw: Optional[dict]


class AuthMicroservice:
    def __init__(
        self,
        *,
        send_reply: Callable[[str, str, Optional[str]], Optional[str]],
        admin_sender_id: Callable[[], str],
        set_admin_sender_id: Callable[[str], None],
        admin_setup_code: Callable[[], str],
        is_sender_approved: Callable[[str], bool],
        normalize_sender_id: Callable[[str], str],
        add_approved_number: Callable[[str], None],
        generate_auth_code: Callable[[], str],
        get_pending_auth: Callable[[str, datetime], Optional[dict[str, object]]],
        set_pending_auth: Callable[[str, str, datetime], None],
        clear_pending_auth: Callable[[str], None],
        now: Callable[[], datetime],
        extract_requester_identity: Callable[..., tuple[str, str]],
        format_admin_auth_request: Callable[..., str],
    ) -> None:
        self._send_reply = send_reply
        self._admin_sender_id = admin_sender_id
        self._set_admin_sender_id = set_admin_sender_id
        self._admin_setup_code = admin_setup_code
        self._is_sender_approved = is_sender_approved
        self._normalize_sender_id = normalize_sender_id
        self._add_approved_number = add_approved_number
        self._generate_auth_code = generate_auth_code
        self._get_pending_auth = get_pending_auth
        self._set_pending_auth = set_pending_auth
        self._clear_pending_auth = clear_pending_auth
        self._now = now
        self._extract_requester_identity = extract_requester_identity
        self._format_admin_auth_request = format_admin_auth_request

    def handle_whoami(self, *, context: AuthCommandContext) -> tuple[bool, Optional[str]]:
        admin_id = self._admin_sender_id()
        if admin_id:
            self._send_reply(context.chat_id, "✅ Admin already set.", context.message_id)
            return True, None

        parts = context.text.strip().split(None, 1)
        code = parts[1].strip() if len(parts) > 1 else ""
        if code != self._admin_setup_code():
            self._send_reply(context.chat_id, "❌ Invalid setup code.", context.message_id)
            return False, "invalid_setup_code"

        self._set_admin_sender_id(context.sender_id)
        self._send_reply(context.chat_id, f"✅ Admin set to {context.sender_id}.", context.message_id)
        return True, None

    def handle_assistant_auth(self, *, context: AssistantAuthContext) -> tuple[bool, Optional[str]]:
        if context.is_group:
            self._send_reply(context.chat_id, "❌ Please DM me to authenticate.", context.message_id)
            return False, "auth_in_group"

        normalized = self._normalize_sender_id(context.sender_id)
        if self._is_sender_approved(context.sender_id):
            self._send_reply(context.chat_id, "✅ Already approved.", context.message_id)
            return True, None

        parts = context.text.strip().split(None, 1)
        if len(parts) == 1:
            code = self._generate_auth_code()
            self._set_pending_auth(context.sender_id, code, self._now())
            logger.warning("Assistant auth code for %s: %s", normalized, code)
            self._notify_admin_auth_request(
                requester_sender_id=context.sender_id,
                requester_chat_id=context.chat_id,
                requester_normalized_id=normalized,
                requester_contact_name=context.contact_name,
                requester_contact_phone=context.contact_phone,
                raw=context.raw,
                code=code,
            )
            self._send_reply(
                context.chat_id,
                "✅ Auth code generated. Ask the admin for it, then reply: !auth <code>.",
                context.message_id,
            )
            return True, None

        pending = self._get_pending_auth(context.sender_id, self._now())
        if not pending:
            self._send_reply(context.chat_id, "❌ No pending auth request. Send !auth to generate a new code.", context.message_id)
            return False, "auth_not_requested"

        code = parts[1].strip()
        if code != pending.get("code"):
            self._send_reply(context.chat_id, "❌ Invalid auth code. Send !auth to generate a new code.", context.message_id)
            return False, "invalid_auth_code"

        self._add_approved_number(normalized)
        self._clear_pending_auth(context.sender_id)
        self._send_reply(context.chat_id, f"✅ Approved: {normalized}.", context.message_id)
        return True, None

    def authorize_admin_command(
        self,
        *,
        chat_id: str,
        sender_id: str,
        message_id: Optional[str],
    ) -> tuple[bool, Optional[str]]:
        reason = authorize_admin_command(
            admin_sender_id=self._admin_sender_id(),
            sender_id=sender_id,
            send_reply=lambda text: self._send_reply(chat_id, text, message_id),
        )
        return reason is None, reason

    def _notify_admin_auth_request(
        self,
        *,
        requester_sender_id: str,
        requester_chat_id: str,
        requester_normalized_id: str,
        requester_contact_name: Optional[str],
        requester_contact_phone: Optional[str | list[str]],
        raw: Optional[dict],
        code: str,
    ) -> None:
        admin_id = self._admin_sender_id()
        if not admin_id:
            return

        normalized_admin = self._normalize_sender_id(admin_id)
        if requester_normalized_id and requester_normalized_id == normalized_admin:
            return

        name_display, phone_display = self._extract_requester_identity(
            sender_id=requester_sender_id,
            contact_name=requester_contact_name,
            contact_phone=requester_contact_phone,
            raw=raw,
        )

        admin_message = self._format_admin_auth_request(
            code=code,
            sender=requester_sender_id,
            chat=requester_chat_id,
            normalized=requester_normalized_id,
            name=name_display,
            phone=phone_display,
        )
        self._send_reply(admin_id, admin_message, None)
