"""Admin roster endpoint: contacts appear from profiles, not just settings."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin_routes import create_admin_router
from app.database.db import Database
from app.models.memory import ConversationMessage
from app.services.examples_service import ContactExamplesService
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.learning_proposals_service import LearningProposalsService
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.owner_reply_pairing_service import OwnerReplyPairingService
from app.services.persona_service import PersonaService
from app.services.profile_service import ProfileService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService
from app.services.suggestions_service import SuggestionsService

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
    suggestions_service = SuggestionsService(db.suggestions, db.feedback)
    examples_service = ContactExamplesService(db.examples)
    learning_proposals_service = LearningProposalsService(
        db.learning_proposals, examples_service, MagicMock()
    )
    owner_reply_pairing_service = OwnerReplyPairingService(
        db.owner_reply_pairs,
        suggestions_service,
        memory_service,
    )
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
            feedback_repository=db.feedback,
            examples_service=examples_service,
            suggestions_service=suggestions_service,
            owner_reply_pairing_service=owner_reply_pairing_service,
            learning_proposals_service=learning_proposals_service,
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


def test_activity_feed_exposes_metadata_without_prompt_or_reply(tmp_path) -> None:
    with Database(f"sqlite:///{tmp_path / 'activity.db'}") as db:
        client, profile_service, _ = _make_client(db)
        profile_service.get_or_create_profile(7431073781, display_name="Новый контакт")
        db.feedback.add_generation_run(
            {
                "trace_id": "trace-1",
                "user_id": 7431073781,
                "suggestion_id": None,
                "purpose": "draft",
                "provider": "ollama",
                "model": "qwen",
                "prompt_version": "reply-v1",
                "context_policy_version": "context-compiler-v2",
                "response_id": None,
                "input_tokens": 12,
                "output_tokens": 8,
                "cached_tokens": None,
                "latency_ms": 321,
                "finish_reason": "stop",
                "error_code": None,
                "fallback_chain": None,
                "created_at": "2026-07-21T13:42:00+00:00",
            }
        )

        response = client.get("/api/admin/activity")

    assert response.status_code == 200
    recent = response.json()["recent"]
    assert recent[0]["display_name"] == "Новый контакт"
    assert recent[0]["prompt_version"] == "reply-v1"
    assert "messages" not in recent[0]
    assert "draft_text" not in recent[0]


def test_owner_reply_pair_api_requires_explicit_confirmation(tmp_path) -> None:
    with Database(f"sqlite:///{tmp_path / 'pair-api.db'}") as db:
        client, profile_service, _ = _make_client(db)
        profile_service.get_or_create_profile(7431073781, display_name="Новый контакт")
        memory = MemoryService(db.memory)
        suggestions = SuggestionsService(db.suggestions, db.feedback)
        pairing = OwnerReplyPairingService(db.owner_reply_pairs, suggestions, memory)
        memory.record_user_message(7431073781, "Как дела?")
        suggestion = suggestions.record(7431073781, "Как дела?", "Черновик ответа")
        assert suggestion is not None
        owner_message = memory.record_assistant_message(
            7431073781,
            "Всё хорошо, спасибо",
            authored_by="owner",
        )
        pair = pairing.observe_owner_reply(owner_message)
        assert pair is not None

        pending = client.get("/api/admin/owner-reply-pairs")
        assert pending.status_code == 200
        assert pending.json()[0]["owner_reply_text"] == "Всё хорошо, спасибо"
        assert suggestions.get(suggestion.id).status == "pending"

        confirmed = client.post(f"/api/admin/owner-reply-pairs/{pair.id}/confirm")
        assert suggestions.get(suggestion.id).status == "owner_replied"
        retracted = client.post(
            f"/api/admin/owner-reply-pairs/{pair.id}/retract",
            json={"reason": "связь неверная"},
        )
        assert suggestions.get(suggestion.id).status == "pair_retracted"

    assert confirmed.status_code == 200
    assert confirmed.json() == {"confirmed": True}
    assert retracted.status_code == 200
    assert retracted.json() == {"retracted": True}


def test_learning_proposal_api_requires_explicit_approval(tmp_path) -> None:
    with Database(f"sqlite:///{tmp_path / 'proposal-api.db'}") as db:
        client, profile_service, _ = _make_client(db)
        profile_service.get_or_create_profile(7431073781, display_name="Новый контакт")
        created = client.post(
            "/api/admin/learning-proposals",
            json={
                "user_id": 7431073781,
                "kind": "positive_example",
                "payload": {"contact_message": "Как дела?", "reply_text": "Отлично"},
                "evidence": {"source": "owner reviewed reply"},
            },
        )
        assert created.status_code == 200
        proposal_id = created.json()["id"]
        assert db.examples.list_examples(7431073781) == []

        approved = client.post(f"/api/admin/learning-proposals/{proposal_id}/approve")

    assert approved.status_code == 200
    assert approved.json() == {"approved": True}


def test_contact_detail_exposes_applied_style_layers(tmp_path) -> None:
    from dataclasses import replace

    with Database(f"sqlite:///{tmp_path / 'style-layers-api.db'}") as db:
        client, _, settings_service = _make_client(db)
        settings_service.save_user_settings(
            replace(
                settings_service.get_user_settings(7431073781),
                style_learning_enabled=True,
                persona_preset="friend",
            )
        )
        memory = MemoryService(db.memory)
        memory.set_owner_style_profile("global", "общая манера", covered_through_message_id=3)
        memory.set_owner_style_profile(
            "persona:friend", "манера друзей", covered_through_message_id=4
        )
        memory.set_style_profile(7431073781, "личная деталь", covered_count=5)

        response = client.get("/api/admin/users/7431073781")

    assert response.status_code == 200
    assert response.json()["style_profiles"] == {
        "global": "общая манера",
        "relationship": "манера друзей",
        "contact": "личная деталь",
    }


def test_persona_too_long_returns_422_not_500(tmp_path) -> None:
    """An over-length raw prompt is a validation error (422), not a 500."""
    from app.services.settings_service import PERSONA_PROMPT_MAX_LENGTH

    with Database(f"sqlite:///{tmp_path / 'persona.db'}") as db:
        client, _, _ = _make_client(db)
        too_long = "я" * (PERSONA_PROMPT_MAX_LENGTH + 1)
        resp = client.put(
            "/api/admin/users/5336144564/persona",
            json={"raw_prompt": too_long, "clear_structured": True},
        )

    assert resp.status_code == 422
    assert "at most" in resp.json()["detail"]


def test_contact_messages_endpoint_pages_by_before_id(tmp_path) -> None:
    """History endpoint returns stable dynamic-scroll pages for one contact."""
    from datetime import datetime

    with Database(f"sqlite:///{tmp_path / 'messages.db'}") as db:
        client, profile_service, _ = _make_client(db)
        profile_service.get_or_create_profile(5336144564, display_name="милая")
        saved = [
            db.memory.add_message(
                ConversationMessage(
                    id=0,
                    user_id=5336144564,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"msg {i}",
                    created_at=datetime(2026, 6, 19, 12, i),
                    authored_by="contact" if i % 2 == 0 else "owner",
                )
            )
            for i in range(5)
        ]

        first = client.get("/api/admin/users/5336144564/messages?limit=2")
        assert first.status_code == 200
        first_payload = first.json()
        assert [m["content"] for m in first_payload["messages"]] == ["msg 3", "msg 4"]
        assert first_payload["has_more"] is True
        assert first_payload["next_before_id"] == saved[3].id
        assert first_payload["total"] == 5
        assert first_payload["messages"][0]["authored_by"] == "owner"

        second = client.get(
            f"/api/admin/users/5336144564/messages?limit=2&before_id={first_payload['next_before_id']}"
        )
        assert second.status_code == 200
        second_payload = second.json()
        assert [m["content"] for m in second_payload["messages"]] == ["msg 1", "msg 2"]
        assert second_payload["has_more"] is True
        assert second_payload["next_before_id"] == saved[1].id


def test_export_history_returns_full_chronological_json(tmp_path) -> None:
    """Export returns the whole history oldest-first, ready to load into an LLM."""
    from datetime import datetime

    with Database(f"sqlite:///{tmp_path / 'export.db'}") as db:
        client, profile_service, _ = _make_client(db)
        profile_service.get_or_create_profile(5336144564, display_name="милая")
        for i in range(4):
            db.memory.add_message(
                ConversationMessage(
                    id=0,
                    user_id=5336144564,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"msg {i}",
                    created_at=datetime(2026, 6, 19, 12, i),
                    authored_by="contact" if i % 2 == 0 else "owner",
                )
            )

        resp = client.get("/api/admin/users/5336144564/export")
        assert resp.status_code == 200
        payload = resp.json()

    assert payload["contact"]["user_id"] == 5336144564
    assert payload["contact"]["display_name"] == "милая"
    assert payload["message_count"] == 4
    assert payload["total_messages"] == 4
    assert payload["truncated"] is False
    # Oldest-first, with role + authored_by + content for direct LLM loading
    assert [m["content"] for m in payload["messages"]] == ["msg 0", "msg 1", "msg 2", "msg 3"]
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["authored_by"] == "contact"
    assert payload["messages"][1]["authored_by"] == "owner"


def test_export_send_dms_document_to_owner(tmp_path, monkeypatch) -> None:
    """The send endpoint DMs the history as a .json document to the caller."""
    from datetime import datetime

    import app.api.admin_routes as admin_routes

    sent = {}

    async def fake_send(bot_token, chat_id, filename, content, caption=""):
        sent.update(
            bot_token=bot_token,
            chat_id=chat_id,
            filename=filename,
            content=content,
            caption=caption,
        )

    monkeypatch.setattr(admin_routes, "_send_document_via_bot", fake_send)

    with Database(f"sqlite:///{tmp_path / 'send.db'}") as db:
        client, profile_service, _ = _make_client(db)
        profile_service.get_or_create_profile(5336144564, display_name="милая")
        db.memory.add_message(
            ConversationMessage(
                id=0,
                user_id=5336144564,
                role="user",
                content="привет",
                created_at=datetime(2026, 6, 19, 12, 0),
                authored_by="contact",
            )
        )

        resp = client.post("/api/admin/users/5336144564/export/send")
        assert resp.status_code == 200
        body = resp.json()

    assert body["sent"] is True
    assert body["message_count"] == 1
    assert sent["chat_id"] == ADMIN_ID  # delivered to the owner (the caller)
    assert sent["filename"].endswith(".json")
    payload = json.loads(sent["content"].decode("utf-8"))
    assert payload["messages"][0]["content"] == "привет"
