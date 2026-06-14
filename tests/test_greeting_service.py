"""Tests for daily greeting business logic."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.models.settings import UserSettings
from app.services.greeting_service import GreetingService


class InMemoryGreetingRepository:
    """Simple repository double for GreetingService tests."""

    def __init__(self) -> None:
        self.values: dict[int, date] = {}

    def get_last_greeting_date(self, user_id: int) -> date | None:
        return self.values.get(user_id)

    def set_last_greeting_date(self, user_id: int, greeting_date: date) -> None:
        self.values[user_id] = greeting_date


def _settings(**kwargs: object) -> UserSettings:
    return UserSettings(user_id=42, **kwargs)


def test_first_message_of_day_should_send_and_persist() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))
    now = datetime(2026, 5, 21, 9, 30, tzinfo=ZoneInfo("Europe/Minsk"))

    should_send = service.should_send_greeting(42, _settings(), now=now)

    assert should_send is True
    assert repository.values[42] == date(2026, 5, 21)


def test_second_message_same_day_should_stay_silent() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))
    now = datetime(2026, 5, 21, 9, 30, tzinfo=ZoneInfo("Europe/Minsk"))

    assert service.should_send_greeting(42, _settings(), now=now) is True
    assert service.should_send_greeting(42, _settings(), now=now) is False


def test_next_calendar_day_should_send_again() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))

    assert service.should_send_greeting(
        42,
        _settings(),
        now=datetime(2026, 5, 21, 23, 59, tzinfo=ZoneInfo("Europe/Minsk")),
    )
    assert service.should_send_greeting(
        42,
        _settings(),
        now=datetime(2026, 5, 22, 0, 1, tzinfo=ZoneInfo("Europe/Minsk")),
    )
    assert repository.values[42] == date(2026, 5, 22)


def test_weekly_schedule_only_sends_on_target_weekday() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))
    settings = _settings(greeting_interval="weekly", greeting_weekday=0)

    monday = datetime(2026, 6, 15, 9, 0, tzinfo=ZoneInfo("Europe/Minsk"))
    tuesday = datetime(2026, 6, 16, 9, 0, tzinfo=ZoneInfo("Europe/Minsk"))

    assert service.should_send_greeting(42, settings, now=monday) is True
    assert service.should_send_greeting(42, settings, now=tuesday) is False


def test_monthly_schedule_only_sends_on_target_day() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))
    settings = _settings(greeting_interval="monthly", greeting_day=1)

    first = datetime(2026, 6, 1, 9, 0, tzinfo=ZoneInfo("Europe/Minsk"))
    second = datetime(2026, 6, 2, 9, 0, tzinfo=ZoneInfo("Europe/Minsk"))

    assert service.should_send_greeting(42, settings, now=first) is True
    assert service.should_send_greeting(42, settings, now=second) is False


def test_timezone_aware_date_logic_uses_configured_timezone() -> None:
    repository = InMemoryGreetingRepository()
    service = GreetingService(repository, ZoneInfo("Europe/Minsk"))

    today = service.today(datetime(2026, 5, 20, 22, 30, tzinfo=ZoneInfo("UTC")))

    assert today == date(2026, 5, 21)
