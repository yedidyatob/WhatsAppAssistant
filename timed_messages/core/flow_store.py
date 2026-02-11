from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol


FlowKey = tuple[str, str]
FlowState = dict[str, object]


class FlowStore(Protocol):
    def get(self, key: FlowKey, now: datetime) -> FlowState | None:
        ...

    def set(self, key: FlowKey, value: FlowState) -> None:
        ...

    def clear(self, key: FlowKey) -> None:
        ...


class InMemoryFlowStore:
    def __init__(self, ttl: timedelta) -> None:
        self._ttl = ttl
        self._flows: dict[FlowKey, FlowState] = {}

    def get(self, key: FlowKey, now: datetime) -> FlowState | None:
        flow = self._flows.get(key)
        if not flow:
            return None
        updated_at = flow.get("updated_at")
        if isinstance(updated_at, datetime) and now - updated_at > self._ttl:
            self._flows.pop(key, None)
            return None
        return flow

    def set(self, key: FlowKey, value: FlowState) -> None:
        self._flows[key] = value

    def clear(self, key: FlowKey) -> None:
        self._flows.pop(key, None)
