"""Tests for greeting rules service."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.models.greeting_rule import GreetingRule
from app.services.greeting_rules_service import GreetingRulesService


class InMemoryGreetingRulesRepository:
    def __init__(self) -> None:
        self._rules: dict[int, GreetingRule] = {}
        self._next_id = 1

    def list_rules(self, user_id: int) -> list[GreetingRule]:
        return sorted(
            [rule for rule in self._rules.values() if rule.user_id == user_id],
            key=lambda item: (item.sort_order, item.id),
        )

    def list_enabled_rules(self) -> list[GreetingRule]:
        return [rule for rule in self._rules.values() if rule.enabled]

    def get_rule(self, rule_id: int) -> GreetingRule | None:
        return self._rules.get(rule_id)

    def add_rule(self, rule: GreetingRule) -> GreetingRule:
        created = GreetingRule(
            id=self._next_id,
            user_id=rule.user_id,
            text=rule.text,
            greeting_interval=rule.greeting_interval,
            greeting_hour=rule.greeting_hour,
            greeting_weekday=rule.greeting_weekday,
            greeting_day=rule.greeting_day,
            enabled=rule.enabled,
            sort_order=rule.sort_order,
            last_sent_date=rule.last_sent_date,
        )
        self._rules[self._next_id] = created
        self._next_id += 1
        return created

    def delete_rule(self, rule_id: int) -> None:
        self._rules.pop(rule_id, None)

    def update_rule(self, rule: GreetingRule) -> GreetingRule:
        self._rules[rule.id] = rule
        return rule

    def count_rules(self, user_id: int) -> int:
        return len(self.list_rules(user_id))


def test_add_multiple_rules_for_same_user() -> None:
    service = GreetingRulesService(InMemoryGreetingRulesRepository())
    service.add_rule(42, "Morning", "daily", hour=8)
    service.add_rule(42, "Evening", "daily", hour=20)
    assert len(service.list_rules(42)) == 2


def test_get_due_rules_returns_multiple_at_same_hour() -> None:
    service = GreetingRulesService(InMemoryGreetingRulesRepository())
    service.add_rule(42, "Daily", "daily", hour=8)
    service.add_rule(42, "Monday", "weekly", hour=8, weekday=0)
    now = datetime(2026, 6, 15, 8, 0, tzinfo=ZoneInfo("Europe/Minsk"))
    due = service.get_due_rules(42, now, require_hour=True)
    assert len(due) == 2


def test_mark_sent_prevents_repeat_same_day() -> None:
    repository = InMemoryGreetingRulesRepository()
    service = GreetingRulesService(repository)
    rule = service.add_rule(42, "Morning", "daily", hour=8)
    now = datetime(2026, 6, 15, 8, 0, tzinfo=ZoneInfo("Europe/Minsk"))
    assert service.get_due_rules(42, now, require_hour=True)
    service.mark_sent(rule.id, now.date())
    assert service.get_due_rules(42, now, require_hour=True) == []
