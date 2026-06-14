"""Admin roster endpoint: contacts appear from profiles, not just settings."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin_routes import create_admin_router
from app.database.db import Database
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.persona_service import PersonaService
from app.services.profile_service import ProfileService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService

ADMIN_ID = 100000001


def _make_client(db: Database) -> tuple[TestClient, ProfileService, SettingsService]:
    profile_service = ProfileService(db.profiles, "Europe/Minsk")
    mood_service = MoodService(db.moods)
    memory_service = MemoryService(db.memory, 20)
    settings_service = SettingsService(db.settings, "ru", 9)
    persona_service = PersonaService(
        settings_service=settings_service, owner_name="Way", bot_name="HelloMate"
    )
    greeting_service = GreetingService(db.greetings, None)
    greeting_rules_service = GreetingRulesService(db.greeting_rules)
    reply_service = ReplyService(
        llm_service=None,
        memory_service=memory_service,
        mood_service=mood_service,
        profile_service=profile_service,
        settings_service=settings_service,
        enabled=False,
    )

    app = FastAPI()
    app.include_router(
        create_admin_router(
            bot_token="123:ABC",
            admin_user_ids={ADMIN_ID},
            profile_service=profile_service,
            mood_service=mood_service,
            memory_service=memory_service,
            settings_service=settings_service,
            persona_service=persona_service,
            reply_service=reply_service,
            greeting_service=greeting_service,
            greeting_rules_service=greeting_rules_service,
            event_repository=db.events,
            mini_app_dev=True,  # bypass Telegram auth in tests
            dev_user_id=ADMIN_ID,
        ),
        prefix="/api",
    )
    return TestClient(app), profile_service, settings_service


def test_roster_includes_profile_only_contacts(tmp_path) -> None:
    """A contact who only messaged (profile row, no settings row) must appear."""
    with Database(f"sqlite:///{tmp_path / 'roster.db'}") as db:
        client, profile_service, settings_service = _make_client(db)

        # Contact that only ever messaged — profile created, no settings written
        profile_service.get_or_create_profile(7431073781, display_name="Новый контакт")
        # Contact that was edited — has a settings row
        settings_service.set_business_reply_mode(5336144564, "suggest")
        profile_service.get_or_create_profile(5336144564, display_name="милая")
        # The owner must be excluded
        profile_service.get_or_create_profile(ADMIN_ID, display_name="Way")

        resp = client.get("/api/admin/users")
        assert resp.status_code == 200
        roster = resp.json()

    ids = {row["user_id"] for row in roster}
    assert 7431073781 in ids  # profile-only contact is visible (the reported bug)
    assert 5336144564 in ids  # settings-backed contact still visible
    assert ADMIN_ID not in ids  # owner excluded

    profile_only = next(r for r in roster if r["user_id"] == 7431073781)
    assert profile_only["display_name"] == "Новый контакт"
    assert profile_only["language"] == "ru"  # defaults used when no settings row
