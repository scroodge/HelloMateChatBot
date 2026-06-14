"""Per-user greeting rule models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class GreetingRule:
    """A scheduled greeting with its own text and timing."""

    id: int
    user_id: int
    text: str
    greeting_interval: str = "daily"
    greeting_hour: int = 9
    greeting_weekday: int = 0
    greeting_day: int = 1
    enabled: bool = True
    sort_order: int = 0
    last_sent_date: date | None = None
