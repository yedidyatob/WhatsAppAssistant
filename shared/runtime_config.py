import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict


DEFAULT_COMMON_CONFIG_PATH = os.getenv("WHATSAPP_COMMON_CONFIG_PATH", "config/common_runtime.json")
logger = logging.getLogger(__name__)


class JsonFileConfig:
    def __init__(self, path: str, *, debug_label: str) -> None:
        self._debug_label = debug_label
        self._path = Path(path)
        self._lock = Lock()
        self._data = self._load_from_disk()
        self._last_mtime = self._get_mtime()
        if os.getenv("WHATSAPP_CONFIG_DEBUG", "").lower() == "true":
            message = self._debug_message()
            if message:
                logger.info("[%s] path=%s %s", self._debug_label, self._path, message)
            else:
                logger.info("[%s] path=%s", self._debug_label, self._path)

    def _debug_message(self) -> str:
        return ""

    def _load_from_disk(self) -> Dict[str, Any]:
        if not self._path.exists():
            return self._default_data()
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[%s] failed to parse %s: %s", self._debug_label, self._path, exc)
            return self._default_data()

    def _write_to_disk(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._last_mtime = self._get_mtime()

    def _default_data(self) -> Dict[str, Any]:
        return {}

    def _get_mtime(self) -> float | None:
        try:
            return self._path.stat().st_mtime
        except FileNotFoundError:
            return None

    def _refresh_if_changed(self) -> None:
        current = self._get_mtime()
        if current is None or current == self._last_mtime:
            return
        self._data = self._load_from_disk()
        self._last_mtime = current
        if os.getenv("WHATSAPP_CONFIG_DEBUG", "").lower() == "true":
            message = self._debug_message()
            if message:
                logger.info("[%s] reloaded %s", self._debug_label, message)
            else:
                logger.info("[%s] reloaded", self._debug_label)


class CommonRuntimeConfig(JsonFileConfig):
    def __init__(self, path: str = DEFAULT_COMMON_CONFIG_PATH) -> None:
        super().__init__(path, debug_label="common_config")

    def _debug_message(self) -> str:
        return f"admin={self._data.get('admin_sender_id')!r}"

    def admin_sender_id(self) -> str:
        self._refresh_if_changed()
        return str(self._data.get("admin_sender_id") or "")

    def set_admin_sender_id(self, sender_id: str) -> None:
        with self._lock:
            data = self._load_from_disk()
            data["admin_sender_id"] = sender_id
            self._write_to_disk(data)
            self._data = data

    def approved_numbers(self) -> list[str]:
        self._refresh_if_changed()
        return list(self._data.get("approved_numbers") or [])

    def add_approved_number(self, number: str) -> None:
        if not number:
            return
        with self._lock:
            data = self._load_from_disk()
            approved = list(data.get("approved_numbers") or [])
            if number not in approved:
                approved.append(number)
            data["approved_numbers"] = approved
            self._write_to_disk(data)
            self._data = data

    def remove_approved_number(self, number: str) -> None:
        if not number:
            return
        with self._lock:
            data = self._load_from_disk()
            approved = list(data.get("approved_numbers") or [])
            data["approved_numbers"] = [n for n in approved if n != number]
            self._write_to_disk(data)
            self._data = data

    def _default_data(self) -> Dict[str, Any]:
        return {
            "admin_sender_id": "",
            "approved_numbers": [],
        }


common_runtime_config = CommonRuntimeConfig()


def assistant_mode_enabled() -> bool:
    return os.getenv("WHATSAPP_ASSISTANT_MODE", "").lower() == "true"
