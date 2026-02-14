import os
from datetime import datetime, timezone
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

    def instructions(self) -> dict[str, str]:
        return self._common.instructions()

    def set_instruction(self, service_name: str, instruction: str) -> None:
        self._common.set_instruction(service_name, instruction)

    def openai_daily_token_budget(self) -> int:
        raw = os.getenv("OPENAI_DAILY_TOKEN_BUDGET", "0").strip()
        try:
            budget = int(raw)
        except ValueError:
            return 0
        return max(0, budget)

    def openai_max_completion_tokens(self) -> int:
        raw = os.getenv("OPENAI_MAX_COMPLETION_TOKENS", "1000").strip()
        try:
            value = int(raw)
        except ValueError:
            return 1000
        return max(1, value)

    def reserve_openai_tokens(self, estimate: int) -> tuple[bool, int, int]:
        budget = self.openai_daily_token_budget()
        if budget <= 0:
            return True, 0, budget

        reserved = max(0, int(estimate))
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            data = self._load_from_disk()
            usage = data.get("openai_usage")
            if not isinstance(usage, dict):
                usage = {}

            usage_date = str(usage.get("date") or "")
            used_raw = usage.get("tokens_used")
            try:
                used = int(used_raw)
            except (TypeError, ValueError):
                used = 0

            if usage_date != today:
                used = 0

            if used + reserved > budget:
                data["openai_usage"] = {"date": today, "tokens_used": used}
                self._data = data
                return False, used, budget

            used += reserved
            data["openai_usage"] = {"date": today, "tokens_used": used}
            self._write_to_disk(data)
            self._data = data
            return True, used, budget

    def reconcile_openai_tokens(self, reserved: int, actual: int) -> None:
        budget = self.openai_daily_token_budget()
        if budget <= 0:
            return

        reserved = max(0, int(reserved))
        actual = max(0, int(actual))
        today = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            data = self._load_from_disk()
            usage = data.get("openai_usage")
            if not isinstance(usage, dict):
                usage = {}

            usage_date = str(usage.get("date") or "")
            used_raw = usage.get("tokens_used")
            try:
                used = int(used_raw)
            except (TypeError, ValueError):
                used = 0

            if usage_date != today:
                used = 0

            used = max(0, used - reserved + actual)
            data["openai_usage"] = {"date": today, "tokens_used": used}
            self._write_to_disk(data)
            self._data = data

    def _default_data(self) -> Dict[str, Any]:
        return {
            "allowed_groups": [],
            "openai_usage": {
                "date": "",
                "tokens_used": 0,
            },
        }


runtime_config = SummarizerRuntimeConfig()
