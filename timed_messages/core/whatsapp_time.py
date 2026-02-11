from __future__ import annotations

from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo


def load_timezone(tz_name: str | None) -> ZoneInfo:
    if not tz_name:
        raise ValueError("timezone required; add 'tz:' or set DEFAULT_TIMEZONE")
    try:
        return ZoneInfo(tz_name)
    except Exception as exc:
        raise ValueError(f"invalid timezone '{tz_name}'") from exc


def parse_datetime(value: str, tz_name: str | None, now_utc: datetime) -> datetime:
    value = value.strip()
    lowered = value.lower()
    tz = load_timezone(tz_name)
    now = now_utc.astimezone(tz)

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


def format_datetime(value: datetime, tz_name: str | None) -> str:
    if tz_name:
        try:
            value = value.astimezone(load_timezone(tz_name))
        except Exception:
            pass
    return value.strftime("%Y-%m-%d %H:%M")
