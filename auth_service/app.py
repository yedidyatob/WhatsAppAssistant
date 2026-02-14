import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI
from pydantic import BaseModel, Field

from shared.auth import InMemoryPendingAuthStore, SixDigitAuthCodeGenerator
from shared.auth_service import AuthMicroservice, AuthCommandContext, AssistantAuthContext
from shared.logging_utils import configure_logging
from shared.runtime_config import whatsapp_gateway_url
from shared.auth_runtime_config import runtime_config
from shared.whatsapp_formatting import format_admin_auth_request

log_level = configure_logging()
logger = logging.getLogger(__name__)


class WhatsAppTransport:
    def __init__(self, base_url: str | None = None, timeout_seconds: int = 5):
        self.base_url = base_url or whatsapp_gateway_url()
        self.timeout = timeout_seconds

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        quoted_message_id: str | None = None,
    ) -> str | None:
        payload: Dict[str, str] = {"to": chat_id, "text": text}
        if quoted_message_id:
            payload["quoted_message_id"] = quoted_message_id

        resp = requests.post(f"{self.base_url}/send", json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Gateway error {resp.status_code}: {resp.text}")
        data = resp.json()
        return str(data.get("message_id")) if data.get("message_id") else None


class WhatsAppInboundEvent(BaseModel):
    message_id: str
    timestamp: int = Field(..., description="unix timestamp (seconds)")
    chat_id: str
    sender_id: str
    is_group: bool
    text: Optional[str] = None
    quoted_text: Optional[str] = None
    quoted_message_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str | list[str]] = None
    raw: Optional[Dict[str, Any]] = None


class WhatsAppEventResponse(BaseModel):
    status: str = "ok"
    accepted: bool
    reason: Optional[str] = None


class AuthEventService:
    _auth_ttl = timedelta(minutes=30)

    def __init__(self) -> None:
        self.transport = WhatsAppTransport()
        self.pending_auth_store = InMemoryPendingAuthStore(ttl=self._auth_ttl)
        self.auth_code_generator = SixDigitAuthCodeGenerator()
        self.auth_service = AuthMicroservice(
            send_reply=self._send_reply,
            admin_sender_id=runtime_config.admin_sender_id,
            set_admin_sender_id=runtime_config.set_admin_sender_id,
            admin_setup_code=runtime_config.admin_setup_code,
            is_sender_approved=runtime_config.is_sender_approved,
            normalize_sender_id=runtime_config.normalize_sender_id,
            add_approved_number=runtime_config.add_approved_number,
            generate_auth_code=lambda: self.auth_code_generator.generate(),
            get_pending_auth=self._get_pending_auth,
            set_pending_auth=self._set_pending_auth,
            clear_pending_auth=self._clear_pending_auth,
            now=lambda: datetime.now(timezone.utc),
            extract_requester_identity=self._extract_requester_identity,
            format_admin_auth_request=format_admin_auth_request,
        )

    def handle_inbound_event(self, event: WhatsAppInboundEvent) -> tuple[bool, Optional[str]]:
        text = (event.text or "").strip()
        normalized = text.lower()

        if normalized.startswith("!whoami"):
            return self.auth_service.handle_whoami(
                context=AuthCommandContext(
                    chat_id=event.chat_id,
                    sender_id=event.sender_id,
                    message_id=event.message_id,
                    text=text,
                )
            )

        if normalized.startswith("!auth"):
            return self.auth_service.handle_assistant_auth(
                context=AssistantAuthContext(
                    chat_id=event.chat_id,
                    sender_id=event.sender_id,
                    message_id=event.message_id,
                    text=text,
                    is_group=event.is_group,
                    contact_name=event.contact_name,
                    contact_phone=event.contact_phone,
                    raw=event.raw,
                )
            )

        return False, "auth_command_only"

    def _send_reply(self, chat_id: str, text: str, quoted_message_id: Optional[str]) -> Optional[str]:
        try:
            return self.transport.send_message(chat_id=chat_id, text=text, quoted_message_id=quoted_message_id)
        except Exception:
            logger.exception("Failed sending auth reply")
            return None

    def _get_pending_auth(self, sender_id: str, now: datetime) -> Optional[dict[str, object]]:
        key = runtime_config.normalize_sender_id(sender_id)
        entry = self.pending_auth_store.get(key, now)
        return {"code": entry.code, "updated_at": entry.updated_at} if entry else None

    def _set_pending_auth(self, sender_id: str, code: str, now: datetime) -> None:
        key = runtime_config.normalize_sender_id(sender_id)
        self.pending_auth_store.set(key, code, now)

    def _clear_pending_auth(self, sender_id: str) -> None:
        key = runtime_config.normalize_sender_id(sender_id)
        self.pending_auth_store.clear(key)

    def _extract_requester_identity(
        self,
        *,
        sender_id: str,
        contact_name: Optional[str],
        contact_phone: Optional[str | list[str]],
        raw: Optional[dict],
    ) -> tuple[str, str]:
        raw_contacts = raw.get("contacts") if isinstance(raw, dict) else None
        primary_contact = raw_contacts[0] if isinstance(raw_contacts, list) and raw_contacts else {}

        profile_name = None
        if isinstance(primary_contact, dict):
            profile = primary_contact.get("profile")
            if isinstance(profile, dict):
                profile_name = profile.get("name")
            if not profile_name:
                name_obj = primary_contact.get("name")
                if isinstance(name_obj, dict):
                    profile_name = name_obj.get("formatted_name")

        display_name = str(contact_name or profile_name or "").strip() or "-"

        if isinstance(contact_phone, list):
            values = [str(value).strip() for value in contact_phone if str(value).strip()]
            phone_display = ", ".join(values)
        else:
            phone_display = str(contact_phone or "").strip()

        if not phone_display and isinstance(primary_contact, dict):
            wa_id = str(primary_contact.get("wa_id") or "").strip()
            if wa_id:
                phone_display = wa_id

        if not phone_display:
            normalized_sender = runtime_config.normalize_sender_id(sender_id)
            phone_display = normalized_sender or "-"

        return display_name, phone_display


app = FastAPI()
auth_event_service = AuthEventService()


@app.on_event("startup")
def log_admin_setup() -> None:
    logger.info("Auth commands: !auth / !whoami")
    if runtime_config.admin_sender_id():
        return
    setup_code = runtime_config.admin_setup_code()
    logger.warning("=== Admin Setup Required ===")
    logger.warning("Setup code: %s", setup_code)
    logger.warning("Send this message from your WhatsApp account:")
    logger.warning("!whoami %s", setup_code)
    logger.warning("============================")


@app.post("/whatsapp/events", response_model=WhatsAppEventResponse)
def whatsapp_events(event: WhatsAppInboundEvent):
    accepted, reason = auth_event_service.handle_inbound_event(event)
    return WhatsAppEventResponse(accepted=accepted, reason=reason)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
