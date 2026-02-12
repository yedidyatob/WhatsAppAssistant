from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shared.auth import InMemoryPendingAuthStore

from timed_messages.core.flow_store import InMemoryFlowStore
from timed_messages.core.whatsapp_event_service import WhatsAppEventService
from timed_messages.transport import whatsapp as whatsapp_transport


class _FakeConn:
    def close(self) -> None:
        return None


def _build_service(monkeypatch, flow_store, pending_auth_store):
    monkeypatch.setattr(whatsapp_transport, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(whatsapp_transport, "PostgresScheduledMessageRepository", lambda conn: object())
    monkeypatch.setattr(whatsapp_transport, "TimedMessageService", lambda repo: object())

    router = whatsapp_transport.create_router(
        flow_store=flow_store,
        pending_auth_store=pending_auth_store,
    )
    route = next(route for route in router.routes if route.path == "/whatsapp/events")
    get_event_service = route.dependant.dependencies[0].call

    generator = get_event_service()
    service = next(generator)
    generator.close()
    return service


def test_event_service_dependency_reuses_injected_stores(monkeypatch):
    flow_store = InMemoryFlowStore(ttl=timedelta(minutes=30))
    pending_auth_store = InMemoryPendingAuthStore(ttl=timedelta(minutes=30))

    service_a = _build_service(monkeypatch, flow_store, pending_auth_store)
    service_b = _build_service(monkeypatch, flow_store, pending_auth_store)

    assert service_a.flow_store is flow_store
    assert service_b.flow_store is flow_store
    assert service_a.pending_auth_store is pending_auth_store
    assert service_b.pending_auth_store is pending_auth_store

    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    service_a._start_flow(
        chat_id="chat-1",
        sender_id="sender-1",
        message_id="msg-1",
        timestamp=timestamp,
    )

    flow = service_b._get_active_flow("chat-1", "sender-1", timestamp)
    assert flow is not None
    assert flow["step"] == "to"


def test_create_router_builds_router_with_expected_prefix():
    router = whatsapp_transport.create_router(
        flow_store=InMemoryFlowStore(ttl=WhatsAppEventService._flow_ttl),
        pending_auth_store=InMemoryPendingAuthStore(ttl=WhatsAppEventService._auth_ttl),
    )

    assert router.prefix == "/whatsapp"
