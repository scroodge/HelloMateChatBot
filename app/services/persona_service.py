"""Persona management service (slice 6B + 6C).

Personas describe how the bot should behave when replying to a contact.
Resolution chain (first non-empty wins):
  1. user.persona_prompt     — raw system prompt set by owner (full override)
  2. structured fields       — assembled from preset + relationship + tone + topics + boundaries
  3. global default_persona  — bot-level fallback set via /settings
  4. builtin                 — language-aware fallback from reply_service
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.settings import UserSettings

if TYPE_CHECKING:
    from app.services.settings_service import SettingsService

_DEFAULT_PERSONAS_PATH = Path(__file__).parent.parent.parent / "data" / "personas.json"

DEFAULT_TONE_RU = "тёплый и естественный"
DEFAULT_TONE_EN = "warm and natural"
DEFAULT_RELATIONSHIP_RU = "знакомый"
DEFAULT_RELATIONSHIP_EN = "acquaintance"


def _load_presets(path: Path = _DEFAULT_PERSONAS_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


class PersonaService:
    """Builds and resolves AI persona prompts for a contact."""

    def __init__(
        self,
        settings_service: SettingsService,
        owner_name: str,
        bot_name: str,
        presets_path: Path = _DEFAULT_PERSONAS_PATH,
    ) -> None:
        self._settings = settings_service
        self.owner_name = owner_name
        self.bot_name = bot_name
        self._presets = _load_presets(presets_path)

    # ------------------------------------------------------------------
    # Preset library
    # ------------------------------------------------------------------

    def list_presets(self) -> list[dict]:
        """Return the ordered preset catalog (id, label, description)."""
        return [
            {"id": key, "label": v["label"], "description": v["description"]}
            for key, v in self._presets.items()
        ]

    # ------------------------------------------------------------------
    # Structured persona assembly
    # ------------------------------------------------------------------

    def assemble_from_structured(self, settings: UserSettings, language: str = "ru") -> str | None:
        """Build a system prompt from structured persona fields.

        Returns None if no structured fields are set.
        Language selects the template variant: 'ru' (default) or 'en'.
        """
        if not any(
            [
                settings.persona_preset,
                settings.persona_relationship,
                settings.persona_tone,
                settings.persona_topics,
                settings.persona_boundaries,
            ]
        ):
            return None

        is_ru = language == "ru"
        preset_key = settings.persona_preset or "friend"
        preset = self._presets.get(preset_key, self._presets.get("friend", {}))

        template_key = "system_template_ru" if is_ru else "system_template_en"
        fallback = (
            "Ты — {relationship} {owner_name} по имени {bot_name}. Тон: {tone}."
            if is_ru
            else "You are {owner_name}'s {relationship} named {bot_name}. Tone: {tone}."
        )
        template = preset.get(template_key, preset.get("system_template", fallback))

        relationship = settings.persona_relationship or (
            DEFAULT_RELATIONSHIP_RU if is_ru else DEFAULT_RELATIONSHIP_EN
        )
        tone = settings.persona_tone or (DEFAULT_TONE_RU if is_ru else DEFAULT_TONE_EN)

        prompt = template.format(
            owner_name=self.owner_name,
            bot_name=self.bot_name,
            relationship=relationship,
            tone=tone,
        )

        if settings.persona_topics:
            try:
                topics = json.loads(settings.persona_topics)
                if topics:
                    joined = ", ".join(topics)
                    prompt += (
                        f"\n\nПредпочтительные темы: {joined}."
                        if is_ru
                        else f"\n\nPreferred topics: {joined}."
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        if settings.persona_boundaries:
            try:
                boundaries = json.loads(settings.persona_boundaries)
                if boundaries:
                    joined = ", ".join(boundaries)
                    prompt += (
                        f"\n\nНе обсуждать: {joined}."
                        if is_ru
                        else f"\n\nDo not discuss: {joined}."
                    )
            except (json.JSONDecodeError, TypeError):
                pass

        return prompt

    # ------------------------------------------------------------------
    # Full 4-level resolution chain
    # ------------------------------------------------------------------

    def resolve(
        self,
        user_id: int,
        *,
        language: str = "ru",
        display_name: str | None = None,
    ) -> tuple[str, str]:
        """Return (system_prompt, source) where source is one of:
        'custom_raw', 'structured', 'global', 'builtin'.
        """
        settings = self._settings.get_user_settings(user_id)

        # 1. Raw persona_prompt (full override)
        if settings.persona_prompt and settings.persona_prompt.strip():
            return settings.persona_prompt.strip(), "custom_raw"

        # 2. Structured fields
        structured = self.assemble_from_structured(settings, language=language)
        if structured:
            return structured, "structured"

        # 3. Global default_persona bot setting
        from app.services.settings_service import DEFAULT_PERSONA_BOT_SETTING

        global_persona = self._settings.get_bot_setting(DEFAULT_PERSONA_BOT_SETTING, "").strip()
        if global_persona:
            return global_persona, "global"

        # 4. Builtin language-aware fallback
        from app.services.reply_service import build_persona_prompt

        return build_persona_prompt(language, display_name), "builtin"

    # ------------------------------------------------------------------
    # Write helpers (used by admin API)
    # ------------------------------------------------------------------

    def set_raw_prompt(self, user_id: int, prompt: str | None) -> UserSettings:
        """Set or clear the raw persona_prompt for a user."""
        return self._settings.set_persona_prompt(user_id, prompt)

    def set_structured(
        self,
        user_id: int,
        *,
        preset: str | None = None,
        relationship: str | None = None,
        tone: str | None = None,
        topics: list[str] | None = None,
        boundaries: list[str] | None = None,
    ) -> UserSettings:
        """Persist structured persona fields for a user."""
        current = self._settings.get_user_settings(user_id)
        updated = replace(
            current,
            persona_preset=preset if preset is not None else current.persona_preset,
            persona_relationship=(
                relationship if relationship is not None else current.persona_relationship
            ),
            persona_tone=tone if tone is not None else current.persona_tone,
            persona_topics=(json.dumps(topics) if topics is not None else current.persona_topics),
            persona_boundaries=(
                json.dumps(boundaries) if boundaries is not None else current.persona_boundaries
            ),
        )
        return self._settings.save_user_settings(updated)

    def clear_structured(self, user_id: int) -> UserSettings:
        """Remove all structured persona fields for a user."""
        current = self._settings.get_user_settings(user_id)
        updated = replace(
            current,
            persona_preset=None,
            persona_relationship=None,
            persona_tone=None,
            persona_topics=None,
            persona_boundaries=None,
        )
        return self._settings.save_user_settings(updated)
