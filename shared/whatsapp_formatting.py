from __future__ import annotations


def format_admin_auth_request(
    *,
    code: str,
    sender: str,
    chat: str,
    normalized: str,
    name: str,
    phone: str,
) -> str:
    return (
        "🔐 New assistant auth request\n"
        f"Code: {code}\n"
        f"Sender: {sender}\n"
        f"Chat: {chat}\n"
        f"Normalized: {normalized}\n"
        f"Name: {name}\n"
        f"Phone: {phone}"
    )
