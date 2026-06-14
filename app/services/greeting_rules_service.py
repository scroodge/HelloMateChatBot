"""Business logic for multiple greeting rules per user."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

from app.database.repositories.greeting_rules import GreetingRulesRepository
from app.models.greeting_rule import GreetingRule
from app.models.settings import UserSettings
from app.services.greeting_schedule import GREETING_INTERVALS


class GreetingRulesService:
    """Manage and evaluate multiple scheduled greetings per user."""

    def __init__(self, repository: GreetingRulesRepository) -> None:
        self.repository = repository

    def has_rules(self, user_id: int) -> bool:
        """Return True when a user has one or more greeting rules."""

        return self.repository.count_rules(user_id) > 0

    def list_rules(self, user_id: int) -> list[GreetingRule]:
        """Return all greeting rules for a user."""

        return self.repository.list_rules(user_id)

    def list_enabled_rules(self) -> list[GreetingRule]:
        """Return all enabled greeting rules."""

        return self.repository.list_enabled_rules()

    def add_rule(
        self,
        user_id: int,
        text: str,
        interval: str,
        *,
        hour: int = 9,
        weekday: int = 0,
        day_of_month: int = 1,
    ) -> GreetingRule:
        """Create a new greeting rule."""

        if interval not in GREETING_INTERVALS:
            raise ValueError(f"Unsupported greeting interval: {interval}")
        if not 0 <= hour <= 23:
            raise ValueError("hour must be between 0 and 23")
        if not 0 <= weekday <= 6:
            raise ValueError("weekday must be between 0 and 6")
        if not 1 <= day_of_month <= 31:
            raise ValueError("day_of_month must be between 1 and 31")

        sort_order = self.repository.count_rules(user_id)
        rule = GreetingRule(
            id=0,
            user_id=user_id,
            text=text.strip(),
            greeting_interval=interval,
            greeting_hour=hour,
            greeting_weekday=weekday,
            greeting_day=day_of_month,
            sort_order=sort_order,
        )
        return self.repository.add_rule(rule)

    def delete_rule_by_index(self, user_id: int, index: int) -> GreetingRule | None:
        """Delete a rule by its 1-based position in the user's list."""

        rules = self.list_rules(user_id)
        if index < 1 or index > len(rules):
            return None
        rule = rules[index - 1]
        self.repository.delete_rule(rule.id)
        return rule

    def toggle_rule_by_index(self, user_id: int, index: int, enabled: bool) -> GreetingRule | None:
        """Enable or disable a rule by its 1-based position."""

        rules = self.list_rules(user_id)
        if index < 1 or index > len(rules):
            return None
        rule = rules[index - 1]
        return self.repository.update_rule(replace(rule, enabled=enabled))

    def get_due_rules(
        self,
        user_id: int,
        now: datetime,
        *,
        require_hour: bool = True,
    ) -> list[GreetingRule]:
        """Return rules that should be sent right now."""

        due: list[GreetingRule] = []
        for rule in self.list_rules(user_id):
            if not rule.enabled:
                continue
            if require_hour and now.hour != rule.greeting_hour:
                continue
            if not self._matches_schedule(rule, now):
                continue
            if rule.last_sent_date == now.date():
                continue
            due.append(rule)
        return due

    def mark_sent(self, rule_id: int, sent_date: date) -> None:
        """Persist the last sent date for a rule."""

        rule = self.repository.get_rule(rule_id)
        if rule is None:
            return
        self.repository.update_rule(replace(rule, last_sent_date=sent_date))

    def _matches_schedule(self, rule: GreetingRule, now: datetime) -> bool:
        settings = UserSettings(
            user_id=rule.user_id,
            greeting_interval=rule.greeting_interval,
            greeting_weekday=rule.greeting_weekday,
            greeting_day=rule.greeting_day,
        )
        interval = settings.greeting_interval
        if interval == "weekly":
            return now.weekday() == settings.greeting_weekday
        if interval == "monthly":
            return now.day == settings.greeting_day
        return interval == "daily"
