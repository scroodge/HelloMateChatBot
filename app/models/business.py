"""Telegram Business connection models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class BusinessConnectionRecord:
    """Persisted business bot connection for an owner account."""

    connection_id: str
    owner_user_id: int
    is_enabled: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BusinessChatRecord:
    """Maps a managed private chat to its contact and connection."""

    chat_id: int
    contact_user_id: int
    connection_id: str
    updated_at: datetime
