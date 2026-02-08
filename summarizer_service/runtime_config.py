import os
from typing import Any, Dict, List

from shared.runtime_config import CommonRuntimeConfig, JsonFileConfig


DEFAULT_SUMMARIZER_CONFIG_PATH = os.getenv(
    "WHATSAPP_SUMMARIZER_CONFIG_PATH", "config/summarizer_runtime.json"
)


class SummarizerRuntimeConfig(JsonFileConfig):
    def __init__(
        self,
        path: str = DEFAULT_SUMMARIZER_CONFIG_PATH,
        common: CommonRuntimeConfig | None = None,
    ) -> None:
        self._common = common or CommonRuntimeConfig()
        super().__init__(path, debug_label="summarizer_config")

    def admin_sender_id(self) -> str:
        return self._common.admin_sender_id()

    def allowed_groups(self) -> List[str]:
        self._refresh_if_changed()
        return list(self._data.get("allowed_groups") or [])

    def add_allowed_group(self, group_id: str) -> None:
        with self._lock:
            data = self._load_from_disk()
            groups = list(data.get("allowed_groups") or [])
            if group_id not in groups:
                groups.append(group_id)
            data["allowed_groups"] = groups
            self._write_to_disk(data)
            self._data = data

    def remove_allowed_group(self, group_id: str) -> None:
        with self._lock:
            data = self._load_from_disk()
            groups = list(data.get("allowed_groups") or [])
            data["allowed_groups"] = [g for g in groups if g != group_id]
            self._write_to_disk(data)
            self._data = data

    def normalize_sender_id(self, sender_id: str) -> str:
        return self._common.normalize_sender_id(sender_id)

    def is_sender_approved(self, sender_id: str) -> bool:
        return self._common.is_sender_approved(sender_id)

    def _default_data(self) -> Dict[str, Any]:
        return {"allowed_groups": []}


runtime_config = SummarizerRuntimeConfig()
