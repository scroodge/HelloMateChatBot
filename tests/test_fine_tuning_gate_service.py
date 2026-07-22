"""Fine-tuning readiness gate tests."""

import pytest

from app.services.fine_tuning_gate_service import FineTuningGateService


class FakeSettings:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get_bot_setting(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def set_bot_setting(self, key: str, value: str) -> str:
        self.values[key] = value
        return value


def test_gate_stays_disabled_until_all_owner_confirmations() -> None:
    service = FineTuningGateService(FakeSettings())

    assert service.status()["ready_to_consider"] is False
    assert service.status()["training_enabled"] is False
    with pytest.raises(ValueError, match="prerequisites"):
        service.confirm({"owner_approved_dataset": True})


def test_gate_records_readiness_but_never_enables_training() -> None:
    service = FineTuningGateService(FakeSettings())
    ready = service.confirm(
        {
            "owner_approved_dataset": True,
            "independent_holdout": True,
            "prompt_context_plateau": True,
            "privacy_and_deletion_plan": True,
            "rollback_confirmed": True,
        }
    )

    assert ready["ready_to_consider"] is True
    assert ready["training_enabled"] is False
