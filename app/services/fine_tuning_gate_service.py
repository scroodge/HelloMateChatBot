"""Owner confirmation gate before any fine-tuning work can be considered."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

_KEY = "fine_tuning_gate_v1"
_REQUIRED = (
    "owner_approved_dataset",
    "independent_holdout",
    "prompt_context_plateau",
    "privacy_and_deletion_plan",
    "rollback_confirmed",
)


class FineTuningGateService:
    def __init__(self, settings: object) -> None:
        self._settings = settings

    def status(self) -> dict[str, object]:
        try:
            saved = json.loads(self._settings.get_bot_setting(_KEY, "{}"))
        except json.JSONDecodeError:
            saved = {}
        confirmations = {
            key: bool(saved.get("confirmations", {}).get(key, False)) for key in _REQUIRED
        }
        return {
            "ready_to_consider": all(confirmations.values()),
            "training_enabled": False,
            "confirmations": confirmations,
            "confirmed_at": saved.get("confirmed_at"),
            "note": (
                "Gate only records owner confirmation. It never uploads data, starts training, "
                "or changes the active model."
            ),
        }

    def confirm(self, confirmations: Mapping[str, bool]) -> dict[str, object]:
        missing = [key for key in _REQUIRED if not confirmations.get(key, False)]
        if missing:
            raise ValueError("All fine-tuning prerequisites must be confirmed")
        self._settings.set_bot_setting(
            _KEY,
            json.dumps(
                {
                    "confirmations": {key: True for key in _REQUIRED},
                    "confirmed_at": datetime.now().astimezone().isoformat(),
                }
            ),
        )
        return self.status()
