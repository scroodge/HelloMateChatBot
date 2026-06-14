"""AI reply generation."""

from __future__ import annotations

import logging

from app.i18n import translate
from app.services.llm import LLMService
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService
from app.services.rag_service import RAGService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class ReplyService:
    """Build context-aware replies using memory, mood, and optional RAG."""

    def __init__(
        self,
        llm_service: LLMService,
        memory_service: MemoryService,
        mood_service: MoodService,
        profile_service: ProfileService,
        settings_service: SettingsService,
        rag_service: RAGService | None = None,
        enabled: bool = False,
    ) -> None:
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.mood_service = mood_service
        self.profile_service = profile_service
        self.settings_service = settings_service
        self.rag_service = rag_service
        self.enabled = enabled

    async def generate_reply(self, user_id: int, user_message: str) -> str | None:
        """Return an AI reply or None when AI replies are disabled."""

        if not self.enabled:
            return None

        language = self.settings_service.get_language(user_id)
        try:
            messages = await self._build_messages(user_id, user_message, language)
            reply = await self.llm_service.complete(messages)
            self.memory_service.record_assistant_message(user_id, reply)
            return reply
        except Exception:
            logger.exception("Failed to generate AI reply for user %s", user_id)
            return translate("ai_unavailable", language)

    async def _build_messages(
        self,
        user_id: int,
        user_message: str,
        language: str,
    ) -> list[dict[str, str]]:
        profile = self.profile_service.get_or_create_profile(user_id)
        mood = self.mood_service.latest_mood(user_id)
        summary = self.memory_service.get_summary(user_id)
        rag_context = ""
        if self.rag_service is not None:
            rag_context = await self.rag_service.retrieve_context(user_id, user_message)

        system_prompt = (
            "You are HelloMate, a warm and concise Telegram companion. "
            f"Reply in {language}. Keep answers short and friendly."
        )
        if profile.display_name:
            system_prompt += f" The user's name is {profile.display_name}."
        if mood is not None:
            system_prompt += f" Latest mood: {mood.mood}/5."
        if summary is not None:
            system_prompt += f" Conversation summary: {summary.summary}"
        if rag_context:
            system_prompt += f" Relevant notes: {rag_context}"

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(self.memory_service.as_chat_messages(user_id))
        messages.append({"role": "user", "content": user_message})
        return messages

    async def transcribe_voice(self, provider: object, audio_bytes: bytes) -> str:
        """Transcribe a voice message using the configured provider."""

        if hasattr(provider, "transcribe"):
            return await provider.transcribe(audio_bytes)
        raise RuntimeError("Configured LLM provider does not support transcription.")
