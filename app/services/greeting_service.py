"""Daily greeting business logic."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class GreetingRepository(Protocol):
    """Persistence contract used by GreetingService."""

    def get_last_greeting_date(self, user_id: int) -> date | None:
        """Return the last greeting date for a user, if present."""
        ...

    def set_last_greeting_date(self, user_id: int, greeting_date: date) -> None:
        """Persist the last greeting date for a user."""
        ...


class GreetingService:
    """Decides whether a user should receive today's greeting."""

    def __init__(self, repository: GreetingRepository, timezone: ZoneInfo) -> None:
        self.repository = repository
        self.timezone = timezone

    def today(self, now: datetime | None = None) -> date:
        """Return today's date in the configured timezone."""

        current_time = now or datetime.now(tz=self.timezone)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=self.timezone)
        return current_time.astimezone(self.timezone).date()

    def should_send_greeting(self, user_id: int, now: datetime | None = None) -> bool:
        """Return True and persist state when a user needs today's greeting."""

        greeting_date = self.today(now)
        if self.repository.get_last_greeting_date(user_id) == greeting_date:
            return False

        self.repository.set_last_greeting_date(user_id, greeting_date)
        return True
