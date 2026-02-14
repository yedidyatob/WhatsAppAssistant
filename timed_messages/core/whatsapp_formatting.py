from __future__ import annotations

from datetime import datetime

from .models import ScheduledMessage
from .whatsapp_time import format_datetime


def format_when_prompt(tz_name: str) -> str:
    return (
        "*When?*\nUse YYYY-MM-DD HH:MM\n"
        "Or use HH:MM / 'today HH:MM' / 'tomorrow HH:MM'.\n"
        "For example: today 18:30\n"
        f"(Current time zone: {tz_name})"
    )


def display_recipient(value: str) -> str:
    if "@" in value:
        return value.split("@", 1)[0]
    return value


def format_schedule_reply(
    *,
    scheduled_id: str,
    to_value: str,
    send_at: datetime,
    tz_name: str | None,
) -> str:
    display_at = format_datetime(send_at, tz_name)
    short_id = scheduled_id.replace("-", "")[:12]
    return (
        "✅ Scheduled\n"
        f"ID: {short_id}\n"
        f"To: {display_recipient(to_value)}\n"
        f"At: {display_at}"
    )


def format_list_reply(messages: list[ScheduledMessage], tz_name: str | None) -> str:
    if not messages:
        return "✅ No scheduled messages"

    lines = ["✅ Scheduled messages"]
    for msg in messages:
        when = format_datetime(msg.send_at, tz_name)
        preview = msg.text.strip().replace("\n", " ")
        if len(preview) > 40:
            preview = f"{preview[:37]}..."
        lines.append(f"- {msg.id.hex[:12]} | {when} | {preview}")
    return "\n".join(lines)

