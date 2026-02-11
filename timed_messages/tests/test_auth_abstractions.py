from datetime import datetime, timedelta, timezone

from shared.auth import InMemoryPendingAuthStore, SixDigitAuthCodeGenerator


def test_auth_code_generator_format():
    code = SixDigitAuthCodeGenerator().generate()
    assert len(code) == 6
    assert code.isdigit()


def test_pending_auth_store_roundtrip_and_ttl_expiry():
    store = InMemoryPendingAuthStore(ttl=timedelta(minutes=30))
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    store.set("15550001111", "123456", now)
    entry = store.get("15550001111", now + timedelta(minutes=5))
    assert entry is not None
    assert entry.code == "123456"

    expired = store.get("15550001111", now + timedelta(minutes=31))
    assert expired is None


def test_pending_auth_store_clear():
    store = InMemoryPendingAuthStore(ttl=timedelta(minutes=30))
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    store.set("15550001111", "123456", now)
    store.clear("15550001111")
    assert store.get("15550001111", now + timedelta(minutes=1)) is None
