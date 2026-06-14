"""Tests for PersonaService — preset library, structured assembly, and resolution chain."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.models.settings import UserSettings
from app.services.persona_service import PersonaService


def _settings_service(user_settings: UserSettings | None = None):
    svc = MagicMock()
    if user_settings is not None:
        svc.get_user_settings.return_value = user_settings
    else:
        svc.get_user_settings.return_value = UserSettings(user_id=1)
    svc.get_bot_setting.return_value = ""
    svc.save_user_settings.side_effect = lambda s: s
    svc.set_persona_prompt.side_effect = lambda uid, p: replace(
        svc.get_user_settings(uid), persona_prompt=p
    )
    return svc


def _make_svc(user_settings: UserSettings | None = None, presets_path: Path | None = None):
    ss = _settings_service(user_settings)
    kwargs = {"settings_service": ss, "owner_name": "Alex", "bot_name": "Mate"}
    if presets_path is not None:
        kwargs["presets_path"] = presets_path
    return PersonaService(**kwargs), ss


def test_list_presets_returns_catalog():
    svc, _ = _make_svc()
    presets = svc.list_presets()
    assert len(presets) >= 3
    ids = {p["id"] for p in presets}
    assert {"friend", "family", "mentor"} <= ids
    for p in presets:
        assert "label" in p and "description" in p


def test_assemble_from_structured_returns_none_for_empty():
    svc, _ = _make_svc()
    result = svc.assemble_from_structured(UserSettings(user_id=1))
    assert result is None


def test_assemble_friend_preset():
    svc, _ = _make_svc()
    settings = UserSettings(
        user_id=1,
        persona_preset="friend",
        persona_relationship="childhood buddy",
        persona_tone="playful",
    )
    prompt = svc.assemble_from_structured(settings)
    assert prompt is not None
    assert "Alex" in prompt
    assert "Mate" in prompt
    assert "childhood buddy" in prompt
    assert "playful" in prompt


def test_assemble_includes_topics_and_boundaries():
    svc, _ = _make_svc()
    settings = UserSettings(
        user_id=1,
        persona_preset="mentor",
        persona_topics=json.dumps(["philosophy", "books"]),
        persona_boundaries=json.dumps(["politics"]),
    )
    prompt = svc.assemble_from_structured(settings)
    assert "philosophy" in prompt
    assert "books" in prompt
    assert "politics" in prompt


def test_resolve_uses_raw_prompt_first():
    settings = UserSettings(user_id=1, persona_prompt="be a pirate")
    svc, _ = _make_svc(settings)
    prompt, source = svc.resolve(1)
    assert prompt == "be a pirate"
    assert source == "custom_raw"


def test_resolve_uses_structured_second():
    settings = UserSettings(user_id=1, persona_preset="friend", persona_tone="warm")
    svc, _ = _make_svc(settings)
    prompt, source = svc.resolve(1)
    assert source == "structured"
    assert "Alex" in prompt


def test_resolve_uses_global_third():
    svc, ss = _make_svc()
    ss.get_bot_setting.return_value = "global system prompt"
    prompt, source = svc.resolve(1)
    assert source == "global"
    assert prompt == "global system prompt"


def test_resolve_falls_back_to_builtin():
    svc, _ = _make_svc()
    prompt, source = svc.resolve(1, language="en")
    assert source == "builtin"
    assert len(prompt) > 10


def test_set_structured_calls_save():
    svc, ss = _make_svc()
    svc.set_structured(1, preset="mentor", relationship="teacher", tone="formal", topics=["AI"])
    ss.save_user_settings.assert_called_once()
    saved: UserSettings = ss.save_user_settings.call_args[0][0]
    assert saved.persona_preset == "mentor"
    assert saved.persona_tone == "formal"
    assert json.loads(saved.persona_topics) == ["AI"]


def test_clear_structured_nulls_all_fields():
    settings = UserSettings(
        user_id=1,
        persona_preset="friend",
        persona_tone="warm",
        persona_topics='["books"]',
    )
    svc, ss = _make_svc(settings)
    svc.clear_structured(1)
    saved: UserSettings = ss.save_user_settings.call_args[0][0]
    assert saved.persona_preset is None
    assert saved.persona_tone is None
    assert saved.persona_topics is None
