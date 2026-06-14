"""Greeting schedule parsing and formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.greeting_rule import GreetingRule
from app.models.settings import UserSettings

GREETING_INTERVALS = frozenset({"daily", "weekly", "monthly"})

WEEKDAY_ALIASES: dict[str, int] = {
    "mon": 0,
    "monday": 0,
    "пн": 0,
    "tue": 1,
    "tuesday": 1,
    "вт": 1,
    "wed": 2,
    "wednesday": 2,
    "ср": 2,
    "thu": 3,
    "thursday": 3,
    "чт": 3,
    "fri": 4,
    "friday": 4,
    "пт": 4,
    "sat": 5,
    "saturday": 5,
    "сб": 5,
    "sun": 6,
    "sunday": 6,
    "вс": 6,
}

WEEKDAY_LABELS_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WEEKDAY_LABELS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

INTERVAL_ALIASES = {
    "ежедневно": "daily",
    "еженедельно": "weekly",
    "ежемесячно": "monthly",
}


@dataclass(frozen=True, slots=True)
class ParsedGreetingSchedule:
    """Parsed schedule fields for a greeting rule."""

    interval: str
    hour: int
    weekday: int
    day_of_month: int
    text: str = ""


def normalize_interval(value: str) -> str | None:
    """Normalize a schedule interval token."""

    normalized = INTERVAL_ALIASES.get(value.strip().lower(), value.strip().lower())
    if normalized in GREETING_INTERVALS:
        return normalized
    return None


def parse_greeting_schedule_args(
    args: list[str],
    *,
    default_hour: int = 9,
    require_text: bool = False,
) -> ParsedGreetingSchedule | None:
    """Parse schedule args shared by addgreeting and setgreetschedule."""

    if not args:
        return None

    interval = normalize_interval(args[0])
    if interval is None:
        return None

    weekday = 0
    day_of_month = 1
    hour = default_hour
    remainder = args[1:]

    if interval == "weekly":
        if not remainder:
            return None
        parsed_weekday = parse_weekday(remainder[0])
        if parsed_weekday is None:
            return None
        weekday = parsed_weekday
        remainder = remainder[1:]
    elif interval == "monthly":
        if not remainder:
            return None
        try:
            day_of_month = int(remainder[0])
        except ValueError:
            return None
        if not 1 <= day_of_month <= 31:
            return None
        remainder = remainder[1:]

    text = ""
    if remainder:
        if remainder[0].isdigit() and 0 <= int(remainder[0]) <= 23:
            hour = int(remainder[0])
            remainder = remainder[1:]
        text = " ".join(remainder).strip()

    if require_text and not text:
        return None

    return ParsedGreetingSchedule(
        interval=interval,
        hour=hour,
        weekday=weekday,
        day_of_month=day_of_month,
        text=text,
    )


def format_rule(rule: GreetingRule, index: int, language: str = "ru") -> str:
    """Return a numbered one-line summary of a greeting rule."""

    schedule = format_schedule(
        UserSettings(
            user_id=rule.user_id,
            greeting_interval=rule.greeting_interval,
            greeting_hour=rule.greeting_hour,
            greeting_weekday=rule.greeting_weekday,
            greeting_day=rule.greeting_day,
        ),
        language,
    )
    state = "вкл" if rule.enabled else "выкл"
    if language != "ru":
        state = "on" if rule.enabled else "off"
    preview = rule.text if len(rule.text) <= 60 else f"{rule.text[:57]}..."
    return f"{index}. [{state}] {schedule} — {preview}"


def parse_weekday(value: str) -> int | None:
    """Parse a weekday token into a 0=Monday index."""

    normalized = value.strip().lower()
    if normalized in WEEKDAY_ALIASES:
        return WEEKDAY_ALIASES[normalized]
    if normalized.isdigit():
        weekday = int(normalized)
        if 0 <= weekday <= 6:
            return weekday
    return None


def format_schedule(settings: UserSettings, language: str = "ru") -> str:
    """Return a human-readable greeting schedule."""

    hour = settings.greeting_hour
    if settings.greeting_interval == "weekly":
        labels = WEEKDAY_LABELS_RU if language == "ru" else WEEKDAY_LABELS_EN
        weekday = labels[settings.greeting_weekday]
        if language == "ru":
            return f"еженедельно, {weekday} в {hour:02d}:00"
        return f"weekly on {weekday} at {hour:02d}:00"

    if settings.greeting_interval == "monthly":
        if language == "ru":
            return f"ежемесячно, {settings.greeting_day}-го числа в {hour:02d}:00"
        return f"monthly on day {settings.greeting_day} at {hour:02d}:00"

    if language == "ru":
        return f"ежедневно в {hour:02d}:00"
    return f"daily at {hour:02d}:00"
