"""Lightweight JSON-based internationalization."""

from __future__ import annotations

import json
from pathlib import Path

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_LOCALES: dict[str, dict[str, str]] = {}


def _load_locales() -> None:
    if _LOCALES:
        return
    for path in _LOCALES_DIR.glob("*.json"):
        _LOCALES[path.stem] = json.loads(path.read_text(encoding="utf-8"))


def supported_languages() -> list[str]:
    """Return supported locale codes."""

    _load_locales()
    return sorted(_LOCALES)


def translate(key: str, language: str = "ru", **kwargs: object) -> str:
    """Return a localized string, falling back to Russian then the key."""

    _load_locales()
    text = _LOCALES.get(language, {}).get(key)
    if text is None:
        text = _LOCALES.get("ru", {}).get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
