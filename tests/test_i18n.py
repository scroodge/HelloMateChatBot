"""Tests for i18n helpers."""

from __future__ import annotations

from app.i18n import language_name, supported_languages, translate


def test_translate_returns_russian_default() -> None:
    assert "HelloMate" in translate("about_message", "ru")


def test_translate_falls_back_to_key() -> None:
    assert translate("missing_key", "ru") == "missing_key"


def test_supported_languages_contains_ru_and_en() -> None:
    languages = supported_languages()
    assert "ru" in languages
    assert "en" in languages


def test_language_name_maps_supported_codes() -> None:
    assert language_name("ru") == "Russian"
    assert language_name("en") == "English"
    assert language_name("de") == "de"
