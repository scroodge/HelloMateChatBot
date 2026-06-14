"""Tests for conversation starter service."""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.services.conversation_starter_service import ConversationStarterService


def test_pick_returns_none_when_file_missing(tmp_path: Path) -> None:
    service = ConversationStarterService(tmp_path / "missing.json")
    assert service.pick() is None


def test_pick_returns_random_starter(tmp_path: Path) -> None:
    starters_path = tmp_path / "starters.json"
    starters_path.write_text(json.dumps(["A", "B", "C"]), encoding="utf-8")
    service = ConversationStarterService(starters_path, rng=random.Random(1))
    first = service.pick()
    assert first in {"A", "B", "C"}
