"""Tests for greeting schedule helpers."""

from __future__ import annotations

from app.models.settings import UserSettings
from app.services.greeting_schedule import (
    format_schedule,
    parse_greeting_schedule_args,
    parse_weekday,
)


def test_parse_weekday_accepts_aliases() -> None:
    assert parse_weekday("mon") == 0
    assert parse_weekday("пн") == 0
    assert parse_weekday("6") == 6


def test_parse_greeting_schedule_args_with_text() -> None:
    parsed = parse_greeting_schedule_args(
        ["daily", "8", "Привет", "дочурка!"],
        require_text=True,
    )
    assert parsed is not None
    assert parsed.hour == 8
    assert parsed.text == "Привет дочурка!"


def test_format_schedule_daily_russian() -> None:
    settings = UserSettings(user_id=1, greeting_hour=8)
    assert format_schedule(settings, "ru") == "ежедневно в 08:00"


def test_format_schedule_weekly_russian() -> None:
    settings = UserSettings(user_id=1, greeting_interval="weekly", greeting_weekday=0, greeting_hour=9)
    assert format_schedule(settings, "ru") == "еженедельно, пн в 09:00"


def test_format_schedule_monthly_russian() -> None:
    settings = UserSettings(user_id=1, greeting_interval="monthly", greeting_day=14, greeting_hour=7)
    assert format_schedule(settings, "ru") == "ежемесячно, 14-го числа в 07:00"
