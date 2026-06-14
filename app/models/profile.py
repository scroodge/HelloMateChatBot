"""User profile models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class UserProfile:
    """Persistent user profile data."""

    user_id: int
    display_name: str | None
    timezone_override: str | None
    created_at: datetime
    last_seen_at: datetime
