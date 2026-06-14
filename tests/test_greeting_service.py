"""Tests for daily greeting business logic."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.greeting_service import GreetingService


class InMemoryGreetingRepository:
    """Simple repository double for GreetingService tests."""

    def __init__(self) -> None:
        self.values: dict[int, date] = {}

    def get_last_greeting_date(self, user_id: int) -> date | None:
        return self.values.get(user_id)

    def set_last_greeting_date(self, user_id: int, greeting_date: date) -> None:
        self.values[user_id] = greeting_date


def test_first_message_of_day_should_send_and_persist() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))

    should_send = service.should_send_greeting(
        user_id=42,
        now=datetime(2026, 5, 21, 9, 30, tzinfo=ZoneInfo("Europe/Minsk")),
    )

    assert should_send is True
    assert repository.values[42] == date(2026, 5, 21)


def test_second_message_same_day_should_stay_silent() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))
    now = datetime(2026, 5, 21, 9, 30, tzinfo=ZoneInfo("Europe/Minsk"))

    assert service.should_send_greeting(user_id=42, now=now) is True
    assert service.should_send_greeting(user_id=42, now=now) is False


def test_next_calendar_day_should_send_again() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))

    assert service.should_send_greeting(
        user_id=42,
        now=datetime(2026, 5, 21, 23, 59, tzinfo=ZoneInfo("Europe/Minsk")),
    )
    assert service.should_send_greeting(
        user_id=42,
        now=datetime(2026, 5, 22, 0, 1, tzinfo=ZoneInfo("Europe/Minsk")),
    )
    assert repository.values[42] == date(2026, 5, 22)


def test_timezone_aware_date_logic_uses_configured_timezone() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))

    today = service.today(datetime(2026, 5, 20, 22, 30, tzinfo=ZoneInfo("UTC")))

    assert today == date(2026, 5, 21)
