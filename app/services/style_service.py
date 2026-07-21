"""Owner writing-style learning (Phase 12).

Builds a per-contact description of how the *owner* writes to that specific
contact, learned only from real owner-authored replies (authored_by="owner",
i.e. typed by the human in suggest/off mode — never AI-generated text, which
would be circular). The profile is refreshed incrementally in the background,
opt-in per contact, and injected into the reply prompt so the bot mimics the
owner's tone — but always subordinate to the per-contact openness dial.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.llm import LLMService, complete_text
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

AGGREGATE_STYLE_BATCH_SIZE = 100


def _build_style_messages(
    existing_profile: str | None,
    owner_messages: list[str],
    language: str,
    max_chars: int,
) -> list[dict[str, str]]:
    """Build the LLM prompt that folds new owner replies into the style profile."""

    if language == "ru":
        system = (
            "Ты анализируешь манеру письма автора по его реальным сообщениям и "
            "ведёшь её краткое описание (стиль, а не содержание). Опиши: длину "
            "фраз, тон, типичные слова и обороты, употребление сленга, эмодзи, "
            "пунктуации, заглавных букв, обращений. Без преамбул и примеров — "
            f"только описание стиля, не длиннее ~{max_chars} символов."
        )
        intro_prev = "Текущее описание стиля:"
        intro_new = "Новые сообщения автора:"
        ask = "Верни обновлённое единое описание стиля."
    else:
        system = (
            "You analyse an author's writing style from their real messages and "
            "maintain a short description of it (style, not content). Describe: "
            "sentence length, tone, typical words/phrases, slang, emoji, "
            "punctuation, capitalisation, forms of address. No preamble, no "
            f"examples — only the style description, at most ~{max_chars} characters."
        )
        intro_prev = "Current style description:"
        intro_new = "New author messages:"
        ask = "Return the updated single style description."

    lines: list[str] = []
    if existing_profile:
        lines.append(f"{intro_prev}\n{existing_profile}\n")
    lines.append(intro_new)
    for msg in owner_messages:
        lines.append(f"- {msg}")
    lines.append("")
    lines.append(ask)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(lines)},
    ]


class StyleService:
    """Maintain an incremental per-contact owner-style profile."""

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        llm_service: LLMService,
        settings_service: SettingsService,
        refresh_interval: int,
        max_chars: int,
        enabled: bool,
    ) -> None:
        self.memory_service = memory_service
        self.llm_service = llm_service
        self.settings_service = settings_service
        self.refresh_interval = max(1, refresh_interval)
        self.max_chars = max_chars
        self.enabled = enabled
        self._in_progress: set[int] = set()
        self._aggregate_in_progress: set[str] = set()
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule_refresh(self, user_id: int) -> None:
        """Fire-and-forget a style refresh on the running event loop."""
        if not self.enabled:
            return
        try:
            task = asyncio.create_task(self.maybe_refresh(user_id))
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def maybe_refresh(self, user_id: int) -> None:
        """Refresh the style profile if enough new owner replies have arrived."""

        if not self.enabled or user_id in self._in_progress:
            return
        settings = self.settings_service.get_user_settings(user_id)
        if not settings.style_learning_enabled:
            return  # only spend LLM calls on opted-in contacts

        # These aggregates are built only from contacts whose owner-style learning
        # is enabled. A new contact can therefore inherit a global baseline even
        # before it has enough personal owner replies.
        source_settings = [
            item
            for item in self.settings_service.list_all_user_settings()
            if item.style_learning_enabled
        ]
        source_user_ids = {item.user_id for item in source_settings}
        await self._maybe_refresh_aggregate("global", source_user_ids, settings.language)
        if scope_key := _relationship_scope_key(settings):
            relationship_user_ids = {
                item.user_id
                for item in source_settings
                if _relationship_scope_key(item) == scope_key
            }
            await self._maybe_refresh_aggregate(
                scope_key,
                relationship_user_ids,
                settings.language,
            )

        total_owner = self.memory_service.count_owner_messages(user_id)
        existing = self.memory_service.get_style_profile(user_id)
        covered = existing.covered_count if existing else 0
        delta = total_owner - covered
        if delta < self.refresh_interval:
            return

        self._in_progress.add(user_id)
        try:
            new_messages = self.memory_service.owner_messages_slice(
                user_id, offset=covered, limit=delta
            )
            if not new_messages:
                return
            language = self.settings_service.get_language(user_id)
            prompt = _build_style_messages(
                existing.profile if existing else None,
                [m.content for m in new_messages],
                language,
                self.max_chars,
            )
            profile = (
                await complete_text(
                    self.llm_service, prompt, purpose="style", contact_user_id=user_id
                )
            ).strip()
            if not profile:
                return
            self.memory_service.set_style_profile(
                user_id, profile[: self.max_chars], covered_count=total_owner
            )
            logger.info(
                "Style profile refreshed for contact %s (covered %d owner msgs)",
                user_id,
                total_owner,
            )
        except Exception:
            logger.exception("Failed to refresh style profile for contact %s", user_id)
        finally:
            self._in_progress.discard(user_id)

    async def _maybe_refresh_aggregate(
        self,
        scope_key: str,
        source_user_ids: set[int],
        language: str,
    ) -> None:
        """Incrementally refresh an opted-in global or relationship style layer."""
        if not source_user_ids or scope_key in self._aggregate_in_progress:
            return
        self._aggregate_in_progress.add(scope_key)
        try:
            existing = self.memory_service.get_owner_style_profile(scope_key)
            watermark = existing.covered_through_message_id if existing else 0
            new_messages = self.memory_service.owner_messages_after_id(
                source_user_ids,
                after_id=watermark,
                limit=AGGREGATE_STYLE_BATCH_SIZE,
            )
            if len(new_messages) < self.refresh_interval:
                return
            prompt = _build_style_messages(
                existing.profile if existing else None,
                [message.content for message in new_messages],
                language,
                self.max_chars,
            )
            profile = (
                await complete_text(
                    self.llm_service,
                    prompt,
                    purpose="style",
                    contact_user_id=None,
                )
            ).strip()
            if not profile:
                return
            self.memory_service.set_owner_style_profile(
                scope_key,
                profile[: self.max_chars],
                covered_through_message_id=new_messages[-1].id or watermark,
            )
            logger.info("Owner style profile refreshed for %s", scope_key)
        except Exception:
            logger.exception("Failed to refresh owner style profile for %s", scope_key)
        finally:
            self._aggregate_in_progress.discard(scope_key)


def _relationship_scope_key(settings: object) -> str | None:
    """Stable style scope: preset first, then a normalized relationship label."""
    preset = (getattr(settings, "persona_preset", None) or "").strip().casefold()
    if preset:
        return f"persona:{preset}"
    relationship = (getattr(settings, "persona_relationship", None) or "").strip().casefold()
    return f"relationship:{relationship[:80]}" if relationship else None
