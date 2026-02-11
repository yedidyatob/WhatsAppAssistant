from __future__ import annotations

import re
from urllib.parse import quote

from .models import ScheduledMessage


def format_assistant_delivery(msg: ScheduledMessage) -> str:
    link = build_whatsapp_link(msg.chat_id, msg.text)
    to_display = display_chat_id(msg.chat_id)
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


def build_whatsapp_link(chat_id: str, text: str) -> str | None:
    digits = re.sub(r"\D", "", chat_id or "")
    if not digits:
        return None
    encoded = quote(text or "", safe="")
    return f"https://wa.me/{digits}?text={encoded}"


def display_chat_id(value: str) -> str:
    if "@" in value:
        return value.split("@", 1)[0]
    return value
