from __future__ import annotations

import re
from typing import Optional


def normalize_recipient(
    value: str,
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


def normalize_contact_phone(
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


def extract_id_prefix(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"\b([0-9a-fA-F]{12})\b", text)
    return match.group(1) if match else None
