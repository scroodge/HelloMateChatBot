"""Owner personal-assistant mode.

A separate, owner-only conversational mode in the bot's direct chat. Unlike
the Business companion (which drafts replies to contacts), this lets the owner
talk to the bot as a personal assistant under a chosen persona (e.g. an English
teacher).

Key isolation guarantee: each assistant profile keeps its conversation under a
dedicated negative memory key (``-(BASE + profile_id)``), so assistant chatter
never lands in any contact's memory, facts, style, or recall. Telegram user ids
are positive, so the negative namespace can never collide with a real contact.
"""

from __future__ import annotations

import logging
import re

from app.database.repositories.assistant import AssistantProfilesRepository
from app.models.assistant import AssistantProfile
from app.services.llm import LLMService, complete_text
from app.services.memory_service import MemoryService
from app.services.reply_service import _sanitize_reply
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Negative + large so assistant memory keys never collide with real (positive)
# Telegram user ids used for contacts.
_MEMORY_BASE = 10_000_000_000_000

# Validation bounds for profile name / persona.
_NAME_RE = re.compile(r"^[a-zA-Zа-яёА-ЯЁ0-9 _-]{1,30}$")
MAX_PERSONA_CHARS = 2000


def _active_key(owner_id: int) -> str:
    return f"assistant_active:{owner_id}"


class AssistantService:
    """Manage owner assistant profiles, active state, and reply generation."""

    def __init__(
        self,
        *,
        repository: AssistantProfilesRepository,
        memory_service: MemoryService,
        llm_service: LLMService,
        settings_service: SettingsService,
        enabled: bool = True,
    ) -> None:
        self.repository = repository
        self.memory_service = memory_service
        self.llm_service = llm_service
        self.settings_service = settings_service
        self.enabled = enabled

    # ------------------------------------------------------------------
    # Memory key
    # ------------------------------------------------------------------

    @staticmethod
    def memory_key(profile_id: int) -> int:
        return -(_MEMORY_BASE + profile_id)

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def list_profiles(self, owner_id: int) -> list[AssistantProfile]:
        return self.repository.list_profiles(owner_id)

    def create_or_update(self, owner_id: int, name: str, persona: str) -> AssistantProfile:
        name = name.strip()
        persona = persona.strip()
        if not _NAME_RE.match(name):
            raise ValueError("Имя профиля: буквы/цифры/пробел/_/-, до 30 символов.")
        if not persona:
            raise ValueError("Опиши персону (системный промпт).")
        if len(persona) > MAX_PERSONA_CHARS:
            raise ValueError(f"Персона должна быть ≤ {MAX_PERSONA_CHARS} символов.")
        return self.repository.upsert(owner_id, name, persona)

    def delete(self, owner_id: int, name: str) -> bool:
        profile = self.repository.get_by_name(owner_id, name.strip())
        if profile is None:
            return False
        # If the deleted profile was active, turn the assistant off.
        active = self.active_profile(owner_id)
        if active is not None and active.id == profile.id:
            self.set_active(owner_id, None)
        if profile.id is not None:
            self.memory_service.clear_messages(self.memory_key(profile.id))
        self.repository.delete(owner_id, name.strip())
        return True

    # ------------------------------------------------------------------
    # Active state
    # ------------------------------------------------------------------

    def active_profile(self, owner_id: int) -> AssistantProfile | None:
        raw = self.settings_service.get_bot_setting(_active_key(owner_id), "")
        if not raw:
            return None
        try:
            profile_id = int(raw)
        except ValueError:
            return None
        return self.repository.get_by_id(profile_id)

    def is_active(self, owner_id: int) -> bool:
        return self.enabled and self.active_profile(owner_id) is not None

    def set_active(self, owner_id: int, profile_id: int | None) -> None:
        self.settings_service.set_bot_setting(
            _active_key(owner_id), "" if profile_id is None else str(profile_id)
        )

    def activate_by_name(self, owner_id: int, name: str) -> AssistantProfile | None:
        profile = self.repository.get_by_name(owner_id, name.strip())
        if profile is None or profile.id is None:
            return None
        self.set_active(owner_id, profile.id)
        return profile

    def reset_history(self, owner_id: int) -> bool:
        profile = self.active_profile(owner_id)
        if profile is None or profile.id is None:
            return False
        self.memory_service.clear_messages(self.memory_key(profile.id))
        return True

    # ------------------------------------------------------------------
    # Reply
    # ------------------------------------------------------------------

    async def reply(self, owner_id: int, user_message: str) -> str | None:
        """Generate an assistant reply for the active profile, or None.

        Records both the user message and the reply into the profile's isolated
        memory so the conversation persists across turns.
        """
        if not self.enabled:
            return None
        profile = self.active_profile(owner_id)
        if profile is None or profile.id is None:
            return None

        key = self.memory_key(profile.id)
        history = self.memory_service.as_chat_messages(key)
        messages = [
            {"role": "system", "content": profile.persona},
            *history,
            {"role": "user", "content": user_message},
        ]
        try:
            reply = _sanitize_reply(
                await complete_text(
                    self.llm_service, messages, purpose="assistant", contact_user_id=owner_id
                )
            )
        except Exception:
            logger.exception("Assistant reply failed for owner %s", owner_id)
            return None

        # Persist the exchange (user then assistant) into the isolated thread.
        self.memory_service.record_user_message(key, user_message)
        self.memory_service.record_assistant_message(key, reply, authored_by="bot")
        return reply
