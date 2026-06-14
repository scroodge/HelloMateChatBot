"""Random conversation starter selection."""

from __future__ import annotations

import json
import random
from pathlib import Path


class ConversationStarterService:
    """Pick a random conversation starter from a JSON list."""

    def __init__(self, starters_path: Path, rng: random.Random | None = None) -> None:
        self.starters_path = starters_path
        self._rng = rng or random.Random()
        self._starters = self._load_starters()

    def _load_starters(self) -> list[str]:
        if not self.starters_path.exists():
            return []
        data = json.loads(self.starters_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("Conversation starters file must contain a JSON list.")
        return [str(item) for item in data if str(item).strip()]

    def pick(self) -> str | None:
        """Return a random starter or None when none are configured."""

        if not self._starters:
            return None
        return self._rng.choice(self._starters)
