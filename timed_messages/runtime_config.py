import os
from typing import Any, Dict

from shared.runtime_config import CommonRuntimeConfig, JsonFileConfig


DEFAULT_TIMED_MESSAGES_CONFIG_PATH = os.getenv(
    "WHATSAPP_TIMED_MESSAGES_CONFIG_PATH", "config/timed_messages_runtime.json"
)


class TimedMessagesRuntimeConfig(JsonFileConfig):
    def __init__(
        self,
        path: str = DEFAULT_TIMED_MESSAGES_CONFIG_PATH,
        common: CommonRuntimeConfig | None = None,
    ) -> None:
        self._common = common or CommonRuntimeConfig()
        super().__init__(path, debug_label="timed_messages_config")

    def admin_sender_id(self) -> str:
        return self._common.admin_sender_id()

    def admin_setup_code(self) -> str:
        self._refresh_if_changed()
        code = str(self._data.get("admin_setup_code") or "")
        if code:
            return code
        code = self._generate_setup_code()
        with self._lock:
            data = self._load_from_disk()
            data["admin_setup_code"] = code
            self._write_to_disk(data)
        self._data = data
        return code

    def approved_numbers(self) -> list[str]:
        return self._common.approved_numbers()

    def add_approved_number(self, number: str) -> None:
        self._common.add_approved_number(number)

    def remove_approved_number(self, number: str) -> None:
        self._common.remove_approved_number(number)

    def scheduling_group(self) -> str:
        self._refresh_if_changed()
        return str(self._data.get("group_id") or "")

    def set_scheduling_group(self, group_id: str) -> None:
        with self._lock:
            data = self._load_from_disk()
            data["group_id"] = group_id
            self._write_to_disk(data)
            self._data = data

    def clear_scheduling_group(self) -> None:
        with self._lock:
            data = self._load_from_disk()
            data["group_id"] = ""
            self._write_to_disk(data)
            self._data = data

    def set_admin_sender_id(self, sender_id: str) -> None:
        self._common.set_admin_sender_id(sender_id)
        with self._lock:
            data = self._load_from_disk()
            data["admin_setup_code"] = ""
            self._write_to_disk(data)
            self._data = data

    def _generate_setup_code(self) -> str:
        return f"{int.from_bytes(os.urandom(3), 'big') % 1_000_000:06d}"

    def _default_data(self) -> Dict[str, Any]:
        return {"group_id": "", "admin_setup_code": ""}


runtime_config = TimedMessagesRuntimeConfig()
