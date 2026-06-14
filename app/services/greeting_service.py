"""Daily greeting business logic."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.database.repositories.greeting import GreetingRepository
from app.models.settings import UserSettings


class GreetingService:
    """Decides whether a user should receive a scheduled greeting."""

    def __init__(self, repository: GreetingRepository, timezone: ZoneInfo) -> None:
        self.repository = repository
        self.timezone = timezone

    def today(self, now: datetime | None = None) -> date:
        """Return today's date in the configured timezone."""

        current_time = self._normalize_now(now)
        return current_time.date()

    def should_send_greeting(
        self,
        user_id: int,
        settings: UserSettings,
        now: datetime | None = None,
    ) -> bool:
        """Return True and persist state when a user should receive a greeting."""

        current_time = self._normalize_now(now)
        today = current_time.date()

        if not self._matches_schedule(settings, current_time):
            return False

        if self.repository.get_last_greeting_date(user_id) == today:
            return False

        self.repository.set_last_greeting_date(user_id, today)
        return True

    def _matches_schedule(self, settings: UserSettings, now: datetime) -> bool:
        interval = settings.greeting_interval
        if interval == "weekly":
            return now.weekday() == settings.greeting_weekday
        if interval == "monthly":
            return now.day == settings.greeting_day
        return interval == "daily"

    def _normalize_now(self, now: datetime | None) -> datetime:
        current_time = now or datetime.now(tz=self.timezone)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=self.timezone)
        return current_time.astimezone(self.timezone)

    def get_last_greeting_date(self, user_id: int) -> date | None:
        """Return the last greeting date for a user."""

        return self.repository.get_last_greeting_date(user_id)

    def list_user_ids(self) -> list[int]:
        """Return all known user IDs."""

        return self.repository.list_user_ids()
