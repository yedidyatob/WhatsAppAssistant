import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any

import requests
from uuid import UUID

DEFAULT_GATEWAY_URL = "http://whatsapp_gateway:3000"
logger = logging.getLogger(__name__)

# ---------- Outbound ----------
class WhatsAppGatewayError(RuntimeError):
    pass


class WhatsAppTransport:
    def __init__(self, base_url: str | None = None, timeout_seconds: int = 5):
        self.base_url = (
            base_url
            or os.getenv("WHATSAPP_GATEWAY_URL")
            or DEFAULT_GATEWAY_URL
        )
        self.timeout = timeout_seconds

    def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        message_id: UUID | None = None,  # TODO: do we need?
        quoted_message_id: str | None = None,  # TODO: how do we quote messages?
    ) -> None:
        payload = {
            "to": chat_id,
            "text": text,
        }

        if quoted_message_id:
            payload["quoted_message_id"] = quoted_message_id

        if message_id:
            payload["message_id"] = str(message_id)

        try:
            resp = requests.post(
                f"{self.base_url}/send",
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise WhatsAppGatewayError(
                f"Failed to reach WhatsApp gateway: {e}"
            ) from e

        if resp.status_code != 200:
            raise WhatsAppGatewayError(
                f"Gateway error {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        if data.get("status") != "ok":
            raise WhatsAppGatewayError(
                f"Gateway failed: {data}"
            )

# ---------- Inbound ----------
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..core.service import TimedMessageService, WhatsAppEventService
from ..infra.db import get_connection
from ..infra.repo_sql import PostgresScheduledMessageRepository


class WhatsAppInboundEvent(BaseModel):
    message_id: str
    timestamp: int = Field(..., description="unix timestamp (seconds)")
    chat_id: str
    sender_id: str
    is_group: bool
    text: Optional[str] = None
    quoted_text: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

class WhatsAppEventResponse(BaseModel):
    status: str = "ok"
    accepted: bool
    reason: Optional[str] = None


router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def get_event_service():
    conn = get_connection()
    try:
        repo = PostgresScheduledMessageRepository(conn)
        timed_service = TimedMessageService(repo)
        transport = WhatsAppTransport()
        yield WhatsAppEventService(timed_service, transport)
    finally:
        conn.close()


@router.post("/events", response_model=WhatsAppEventResponse)
def receive_whatsapp_event(
    event: WhatsAppInboundEvent,
    service: WhatsAppEventService = Depends(get_event_service),
):
    """
    Inbound WhatsApp event from Baileys.

    Responsibilities:
    - Validate payload
    - Delegate to service layer
    - Return acknowledgment
    """

    try:
        accepted, reason = service.handle_inbound_event(
            message_id=event.message_id,
            chat_id=event.chat_id,
            sender_id=event.sender_id,
            text=event.text,
            quoted_text=event.quoted_text,
            contact_name=event.contact_name,
            contact_phone=event.contact_phone,
            timestamp=datetime.fromtimestamp(event.timestamp),
            is_group=event.is_group,
            raw=event.raw,
        )
    except Exception as e:
        # Transport-level failure (not WhatsApp-visible)
        logger.exception("Failed handling WhatsApp event")
        raise HTTPException(status_code=500, detail=str(e))

    if not accepted:
        logger.warning(
            "WhatsApp event rejected reason=%s chat_id=%s sender_id=%s text=%r",
            reason,
            event.chat_id,
            event.sender_id,
            event.text,
        )

    return WhatsAppEventResponse(
        accepted=accepted,
        reason=reason,
    )
