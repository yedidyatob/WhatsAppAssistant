import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict


DEFAULT_COMMON_CONFIG_PATH = os.getenv("WHATSAPP_COMMON_CONFIG_PATH", "config/common_runtime.json")


class JsonFileConfig:
    def __init__(self, path: str, *, debug_label: str) -> None:
        self._debug_label = debug_label
        self._path = Path(path)
        self._lock = Lock()
        self._data = self._load_from_disk()
        self._last_mtime = self._get_mtime()
        if os.getenv("WHATSAPP_CONFIG_DEBUG") == "true":
            message = self._debug_message()
            if message:
                print(f"[{self._debug_label}] path={self._path} {message}")
            else:
                print(f"[{self._debug_label}] path={self._path}")

    def _debug_message(self) -> str:
        return ""

    def _load_from_disk(self) -> Dict[str, Any]:
        if not self._path.exists():
            return self._default_data()
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
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
        if os.getenv("WHATSAPP_CONFIG_DEBUG") == "true":
            message = self._debug_message()
            if message:
                print(f"[{self._debug_label}] reloaded {message}")
            else:
                print(f"[{self._debug_label}] reloaded")


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

    def _default_data(self) -> Dict[str, Any]:
        return {"admin_sender_id": ""}


common_runtime_config = CommonRuntimeConfig()
