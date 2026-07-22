"""Safety boundaries for the Phase 23C contact canary."""

from __future__ import annotations

from app.models.reply_decision import ReplyDecision
from app.services.risk_routing_service import RiskRoutingService


class FakeSettings:
    def __init__(self) -> None:
        self.value = "[]"

    def get_bot_setting(self, key: str, default: str) -> str:
        return self.value

    def set_bot_setting(self, key: str, value: str) -> None:
        self.value = value


def _decision(recommended_mode: str) -> ReplyDecision:
    return ReplyDecision(
        "test", "high", "unknown", False, False, recommended_mode, ("test",)
    )


def test_disabled_canary_keeps_configured_mode() -> None:
    service = RiskRoutingService(FakeSettings(), enabled=False)
    service.set_contact(7, True)

    assert service.route_mode(7, "auto", _decision("off")) == "auto"


def test_selected_contact_can_only_be_downgraded() -> None:
    service = RiskRoutingService(FakeSettings(), enabled=True)
    service.set_contact(7, True)

    assert service.route_mode(7, "auto", _decision("suggest")) == "suggest"
    assert service.route_mode(7, "auto", _decision("off")) == "off"
    assert service.route_mode(7, "suggest", _decision("auto")) == "suggest"
    assert service.route_mode(7, "off", _decision("auto")) == "off"


def test_unselected_contact_keeps_configured_mode() -> None:
    service = RiskRoutingService(FakeSettings(), enabled=True)

    assert service.route_mode(7, "auto", _decision("off")) == "auto"
