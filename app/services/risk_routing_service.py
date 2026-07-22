"""Guarded Phase 23C canary routing based on shadow risk decisions."""

from __future__ import annotations

import json

from app.models.reply_decision import ReplyDecision

_CANARY_CONTACTS_KEY = "risk_routing_canary_contacts_v1"


class RiskRoutingService:
    """Can only make selected contacts safer, never more autonomous."""

    def __init__(self, settings: object, *, enabled: bool = False) -> None:
        self._settings = settings
        self.enabled = enabled

    def contacts(self) -> set[int]:
        try:
            values = json.loads(self._settings.get_bot_setting(_CANARY_CONTACTS_KEY, "[]"))
        except json.JSONDecodeError:
            return set()
        return {int(value) for value in values if isinstance(value, int) or str(value).isdigit()}

    def set_contact(self, user_id: int, enabled: bool) -> bool:
        contacts = self.contacts()
        if enabled:
            contacts.add(user_id)
        else:
            contacts.discard(user_id)
        self._settings.set_bot_setting(_CANARY_CONTACTS_KEY, json.dumps(sorted(contacts)))
        return user_id in contacts

    def is_contact_enabled(self, user_id: int) -> bool:
        return self.enabled and user_id in self.contacts()

    def route_mode(self, user_id: int, configured_mode: str, decision: ReplyDecision) -> str:
        if not self.is_contact_enabled(user_id) or configured_mode == "off":
            return configured_mode
        if decision.recommended_mode == "off":
            return "off"
        if configured_mode == "auto" and decision.recommended_mode == "suggest":
            return "suggest"
        return configured_mode
