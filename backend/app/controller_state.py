"""In-process controller state: auto-mode flag + action log (no DB/Redis)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


class ControllerState:
    def __init__(self) -> None:
        self.auto_mode: bool = False
        self.action_log: list[dict] = []
        self._actioned_keys: set[str] = set()

    def set_auto_mode(self, enabled: bool) -> None:
        self.auto_mode = enabled

    def has_actioned(self, key: str) -> bool:
        return key in self._actioned_keys

    def log_action(self, *, recommendation: dict, actor: str, auto: bool) -> dict:
        entry = {
            "id": uuid.uuid4().hex[:8],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "train_number": recommendation["train_number"],
            "train_name": recommendation.get("train_name"),
            "station_code": recommendation["station_code"],
            "severity": recommendation["severity"],
            "predicted_delay": recommendation["predicted_delay"],
            "action": recommendation["suggested_action"],
            "actor": actor,
            "auto": auto,
        }
        self.action_log.insert(0, entry)
        self.action_log[:] = self.action_log[:200]
        self._actioned_keys.add(recommendation["id"])
        return entry


controller_state = ControllerState()
