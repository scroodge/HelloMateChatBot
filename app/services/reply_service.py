"""AI reply generation."""

from __future__ import annotations

import logging
import re

from app.i18n import language_name, translate
from app.services.llm import LLMService
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService
from app.services.rag_service import RAGService
from app.services.settings_service import SettingsService
from app.services.weather_service import WeatherService, is_weather_query

logger = logging.getLogger(__name__)

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def _contains_cjk(text: str) -> bool:
    """Return True when the text includes Chinese/Japanese/Korean characters."""

    return bool(_CJK_PATTERN.search(text))


def build_persona_prompt(language: str, display_name: str | None = None) -> str:
    """Build a system prompt that makes replies feel like the user's own voice."""

    lang = language_name(language)
    if language == "ru":
        prompt = (
            "Ты — личный голос пользователя в приватном Telegram-чате. "
            "Отвечай так, будто это сам пользователь говорит с собой: тепло, прямо, неформально. "
            "Обращайся на «ты», никогда на «вы». "
            "Используй первое лицо, когда это естественно («я думаю», «мне кажется»). "
            "Никогда не представляйся ботом, ИИ или ассистентом. "
            f"Отвечай только на {lang}. "
            "Не используй китайский и не смешивай языки. "
            "Пиши коротко, по-дружески."
        )
    else:
        prompt = (
            "You are the user's personal inner voice in a private Telegram chat. "
            "Reply as if the user is talking to themselves — warm, direct, informal. "
            "Use first person when natural. "
            "Never say you are a bot, AI, or assistant. "
            f"Respond only in {lang}. "
            "Never use Chinese or mixed languages. "
            "Keep answers short and friendly."
        )

    if display_name:
        prompt += f" Имя пользователя: {display_name}." if language == "ru" else f" User name: {display_name}."
    return prompt


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
        weather_service: WeatherService | None = None,
        enabled: bool = False,
    ) -> None:
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.mood_service = mood_service
        self.profile_service = profile_service
        self.settings_service = settings_service
        self.rag_service = rag_service
        self.weather_service = weather_service
        self.enabled = enabled

    async def generate_reply(self, user_id: int, user_message: str) -> str | None:
        """Return an AI reply or None when AI replies are disabled."""

        if not self.enabled:
            return None

        language = self.settings_service.get_language(user_id)
        try:
            messages = await self._build_messages(user_id, user_message, language)
            reply = await self.llm_service.complete(messages)
            if _contains_cjk(reply):
                reply = await self._rewrite_without_cjk(messages, reply, language)
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

        weather_context = ""
        if self.weather_service is not None and is_weather_query(user_message):
            weather_context = await self.weather_service.get_context(language) or ""

        system_prompt = self.settings_service.resolve_persona_prompt(
            user_id, language, profile.display_name
        )
        if mood is not None:
            system_prompt += f" Последнее настроение: {mood.mood}/5." if language == "ru" else f" Latest mood: {mood.mood}/5."
        if summary is not None:
            system_prompt += (
                f" Краткое резюме разговора: {summary.summary}."
                if language == "ru"
                else f" Conversation summary: {summary.summary}."
            )
        if rag_context:
            system_prompt += f" Заметки: {rag_context}." if language == "ru" else f" Relevant notes: {rag_context}."
        if weather_context:
            system_prompt += f" {weather_context}"

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(self.memory_service.as_chat_messages(user_id))
        messages.append({"role": "user", "content": user_message})
        return messages

    async def _rewrite_without_cjk(
        self,
        messages: list[dict[str, str]],
        reply: str,
        language: str,
    ) -> str:
        """Ask the model to rewrite a mixed-language reply in the target language."""

        lang = language_name(language)
        if language == "ru":
            rewrite_request = (
                f"Перепиши предыдущий ответ полностью на {lang}. "
                "Без китайского и других языков. Сохрани тон: на «ты», от первого лица."
            )
        else:
            rewrite_request = (
                f"Rewrite your previous answer entirely in {lang}. "
                "Do not use Chinese or any other language."
            )
        retry_messages = [
            *messages,
            {"role": "assistant", "content": reply},
            {"role": "user", "content": rewrite_request},
        ]
        try:
            rewritten = await self.llm_service.complete(retry_messages)
            if not _contains_cjk(rewritten):
                return rewritten
            logger.warning("LLM still returned CJK characters after rewrite for language %s", language)
        except Exception:
            logger.exception("Failed to rewrite mixed-language reply for language %s", language)
        return reply

    async def transcribe_voice(self, provider: object, audio_bytes: bytes) -> str:
        """Transcribe a voice message using the configured provider."""

        if hasattr(provider, "transcribe"):
            return await provider.transcribe(audio_bytes)
        raise RuntimeError("Configured LLM provider does not support transcription.")
