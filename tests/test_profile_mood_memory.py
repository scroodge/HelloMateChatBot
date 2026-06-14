"""Tests for profile, mood, and memory services."""

from __future__ import annotations

from datetime import datetime

from app.models.memory import ConversationMessage, ConversationSummary
from app.models.mood import MoodEntry
from app.models.profile import UserProfile
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[int, UserProfile] = {}

    def get_profile(self, user_id: int) -> UserProfile | None:
        return self.profiles.get(user_id)

    def upsert_profile(self, profile: UserProfile) -> UserProfile:
        self.profiles[profile.user_id] = profile
        return profile

    def list_profiles(self) -> list[UserProfile]:
        return list(self.profiles.values())


class InMemoryMoodRepository:
    def __init__(self) -> None:
        self.entries: list[MoodEntry] = []
        self._next_id = 1

    def add_mood_entry(self, entry: MoodEntry) -> MoodEntry:
        stored = MoodEntry(
            id=self._next_id,
            user_id=entry.user_id,
            mood=entry.mood,
            note=entry.note,
            recorded_at=entry.recorded_at,
        )
        self._next_id += 1
        self.entries.append(stored)
        return stored

    def list_mood_entries(self, user_id: int, limit: int = 50) -> list[MoodEntry]:
        return [entry for entry in self.entries if entry.user_id == user_id][:limit]


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self.messages: list[ConversationMessage] = []
        self.summaries: dict[int, ConversationSummary] = {}
        self._next_id = 1

    def add_message(self, message: ConversationMessage) -> ConversationMessage:
        stored = ConversationMessage(
            id=self._next_id,
            user_id=message.user_id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
        )
        self._next_id += 1
        self.messages.append(stored)
        return stored

    def list_messages(self, user_id: int, limit: int = 20) -> list[ConversationMessage]:
        items = [message for message in self.messages if message.user_id == user_id]
        return items[-limit:]

    def get_summary(self, user_id: int) -> ConversationSummary | None:
        return self.summaries.get(user_id)

    def set_summary(self, summary: ConversationSummary) -> ConversationSummary:
        self.summaries[summary.user_id] = summary
        return summary


def test_profile_service_creates_profile() -> None:
    now = datetime(2026, 5, 21, 10, 0)
    service = ProfileService(InMemoryProfileRepository(), "Europe/Minsk")
    profile = service.get_or_create_profile(7, display_name="Way", now=now)
    assert profile.user_id == 7
    assert profile.display_name == "Way"


def test_mood_service_records_entry() -> None:
    service = MoodService(InMemoryMoodRepository())
    entry = service.record_mood(7, 4, note="Good day")
    assert entry.mood == 4
    assert service.latest_mood(7) == entry


def test_memory_service_stores_window() -> None:
    service = MemoryService(InMemoryMemoryRepository(), window_size=2)
    service.record_user_message(7, "Hi")
    service.record_assistant_message(7, "Hello")
    service.record_user_message(7, "How are you?")
    messages = service.recent_messages(7)
    assert len(messages) == 2
    assert messages[0].content == "Hello"
    assert messages[1].content == "How are you?"
