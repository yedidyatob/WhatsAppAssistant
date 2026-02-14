import os
from typing import Any, Dict

from shared.runtime_config import CommonRuntimeConfig, JsonFileConfig


DEFAULT_AUTH_CONFIG_PATH = os.getenv(
    "WHATSAPP_AUTH_CONFIG_PATH",
    "config/auth_runtime.json",
)


class AuthRuntimeConfig(JsonFileConfig):
    def __init__(
        self,
        path: str = DEFAULT_AUTH_CONFIG_PATH,
        common: CommonRuntimeConfig | None = None,
    ) -> None:
        self._common = common or CommonRuntimeConfig()
        super().__init__(path, debug_label="auth_config")

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

    def set_admin_sender_id(self, sender_id: str) -> None:
        self._common.set_admin_sender_id(sender_id)
        with self._lock:
            data = self._load_from_disk()
            data["admin_setup_code"] = ""
            self._write_to_disk(data)
            self._data = data

    def normalize_sender_id(self, sender_id: str) -> str:
        return self._common.normalize_sender_id(sender_id)

    def is_sender_approved(self, sender_id: str) -> bool:
        return self._common.is_sender_approved(sender_id)

    def add_approved_number(self, number: str) -> None:
        self._common.add_approved_number(number)

    def _generate_setup_code(self) -> str:
        return f"{int.from_bytes(os.urandom(3), 'big') % 1_000_000:06d}"

    def _default_data(self) -> Dict[str, Any]:
        return {"admin_setup_code": ""}


runtime_config = AuthRuntimeConfig()
