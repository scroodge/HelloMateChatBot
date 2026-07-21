"""AI reply generation."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from app.i18n import language_name, translate
from app.models.context import CompiledContext, ContextBlock
from app.services.context_compiler import ContextCompiler, context_block
from app.services.llm import LLMService, complete_text
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService
from app.services.prompt_registry import CONTEXT_POLICY_VERSION, REPLY_PROMPT_VERSION
from app.services.rag_service import RAGService
from app.services.settings_service import SettingsService
from app.services.weather_service import WeatherService, is_weather_query

logger = logging.getLogger(__name__)

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")


def _contains_cjk(text: str) -> bool:
    """Return True when the text includes Chinese/Japanese/Korean characters."""

    return bool(_CJK_PATTERN.search(text))


def _freshness_at(value: object) -> datetime | None:
    """Keep provenance metadata strict when tests or legacy data omit a timestamp."""

    return value if isinstance(value, datetime) else None


def _relationship_style_scope(settings: object) -> str | None:
    preset = (getattr(settings, "persona_preset", None) or "").strip().casefold()
    if preset:
        return f"persona:{preset}"
    relationship = (getattr(settings, "persona_relationship", None) or "").strip().casefold()
    return f"relationship:{relationship[:80]}" if relationship else None


def _style_layers_prompt(
    language: str,
    *,
    global_profile: str | None,
    relationship_profile: str | None,
    contact_profile: str | None,
) -> str:
    """Compose ordered style layers without letting them overrule safety policy."""
    if language == "ru":
        lines = [
            "Подражай манере письма владельца. Слои ниже идут от общего к частному; "
            "следующий слой уточняет предыдущий. Не нарушай правила точности и открытости."
        ]
        labels = ("Общая манера", "Манера для этой роли", "Особенность этого контакта")
    else:
        lines = [
            "Mimic the owner's writing style. The layers below go from general to specific; "
            "each following layer refines the previous one. Do not override accuracy or openness rules."
        ]
        labels = ("Global baseline", "Role-specific style", "Contact-specific adjustment")
    for label, profile in zip(
        labels,
        (global_profile, relationship_profile, contact_profile),
        strict=True,
    ):
        if profile:
            lines.append(f"{label}: {profile}")
    return " ".join(lines)


# Meta-instruction leakage: a weak model sometimes appends a self-directed
# revision request or AI-disclaimer after the actual reply (e.g. "...can you
# please modify the response to fit the persona and guidelines provided..."),
# or an English instruction tail. We cut the reply at the first such marker.
_META_LEAK = re.compile(
    r"(can you (?:please|kindly)|could you (?:please|kindly)|"
    r"please (?:modify|rewrite|revise|adjust|change|note)|"
    r"(?:modify|rewrite|revise) the (?:response|reply|message|text)|"
    r"to fit the persona|guidelines provided|"
    r"as an ai|i am an ai|i'?m an ai|language model|"
    r"without including|here'?s the (?:revised|modified|updated)|"
    r"\[/?(?:inst|system|user|assistant)\]|<\|.*?\|>)",
    re.IGNORECASE,
)


def _sanitize_reply(text: str) -> str:
    """Strip trailing meta-instruction / role-leak text from a model reply."""

    match = _META_LEAK.search(text)
    if match is None:
        return text
    cut = text[: match.start()].rstrip(" ,;:-\u2014\n\t\"'\u00ab\u00bb()")
    logger.warning("Stripped leaked meta-text from reply (kept %d/%d chars)", len(cut), len(text))
    return cut.strip() or text.strip()


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
        prompt += (
            f" Имя пользователя: {display_name}."
            if language == "ru"
            else f" User name: {display_name}."
        )
    return prompt


def _openness_directive(openness: str, language: str) -> str:
    """Return a strong trailing instruction controlling how open/guarded to be.

    This is appended last to the system prompt so it overrides persona tone and
    any learned style — the owner's lever for not being fully open with everyone.
    """

    if language == "ru":
        directives = {
            "open": (
                " Стиль общения: будь максимально открытым и тёплым, как с близким "
                "человеком; можно делиться личным и эмоциями."
            ),
            "neutral": (
                " Стиль общения: дружелюбно, но умеренно; не раскрывай лишних личных подробностей."
            ),
            "reserved": (
                " Стиль общения: вежливо, но сдержанно и закрыто. Не делись личными "
                "подробностями, не показывай лишних эмоций, отвечай по делу и коротко."
            ),
        }
    else:
        directives = {
            "open": (
                " Communication style: be fully open and warm, as with a close "
                "person; sharing personal things and emotions is fine."
            ),
            "neutral": (
                " Communication style: friendly but measured; do not reveal extra personal details."
            ),
            "reserved": (
                " Communication style: polite but reserved and guarded. Do not share "
                "personal details, keep emotions minimal, answer briefly and to the point."
            ),
        }
    return directives.get(openness, directives["neutral"])


def _accuracy_directive(language: str) -> str:
    if language == "ru":
        return (
            " Приоритет ответа: сначала точно пойми и выполни прямую просьбу "
            "собеседницы. Если она просит объяснить, перевести или уточнить, ответь "
            "по существу; характер, юмор и флирт добавляй только если они не искажают "
            "смысл. Не восстанавливай пропущенный смысл по догадке и не приписывай "
            "владельцу намерения, действия или чувства без опоры на контекст. Если "
            "важного контекста недостаточно, задай один короткий уточняющий вопрос."
        )
    return (
        " Reply priority: first understand and fulfil the contact's direct request "
        "accurately. If they ask for an explanation, translation, or clarification, "
        "answer the substance first; add personality, humour, or flirting only when it "
        "does not distort the meaning. Do not guess missing meaning or attribute "
        "unsupported intentions, actions, or feelings to the owner. If essential context "
        "is missing, ask one short clarifying question."
    )


def _current_user_content(user_message: str, reply_context: str | None, language: str) -> str:
    if not reply_context:
        return user_message
    context = reply_context.strip()[:4000]
    if language == "ru":
        return (
            "Контекст цитаты (это не новое сообщение собеседницы):\n"
            f"{context}\n\nНовое сообщение собеседницы:\n{user_message}"
        )
    return (
        "Quoted context (this is not a new message from the contact):\n"
        f"{context}\n\nContact's new message:\n{user_message}"
    )


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
        facts_service: object | None = None,
        recall_service: object | None = None,
        examples_service: object | None = None,
        learning_proposals_service: object | None = None,
        context_compiler: ContextCompiler | None = None,
        context_token_budget: int = 4000,
        enabled: bool = False,
    ) -> None:
        self.llm_service = llm_service
        self.memory_service = memory_service
        self.mood_service = mood_service
        self.profile_service = profile_service
        self.settings_service = settings_service
        self.rag_service = rag_service
        self.weather_service = weather_service
        self.facts_service = facts_service
        self.recall_service = recall_service
        self.examples_service = examples_service
        self.learning_proposals_service = learning_proposals_service
        self.context_compiler = context_compiler or ContextCompiler(
            token_budget=context_token_budget
        )
        self.enabled = enabled

    async def generate_reply(
        self, user_id: int, user_message: str, *, reply_context: str | None = None
    ) -> str | None:
        """Return an AI reply or None when AI replies are disabled."""

        if not self.enabled:
            return None

        language = self.settings_service.get_language(user_id)
        try:
            messages = await self._build_messages(
                user_id, user_message, language, reply_context=reply_context
            )
            reply = await complete_text(
                self.llm_service,
                messages,
                purpose="reply",
                contact_user_id=user_id,
                prompt_version=REPLY_PROMPT_VERSION,
                context_policy_version=CONTEXT_POLICY_VERSION,
            )
            if _contains_cjk(reply):
                reply = await self._rewrite_without_cjk(messages, reply, language)
            reply = _sanitize_reply(reply)
            self.memory_service.record_assistant_message(user_id, reply, authored_by="bot")
            return reply
        except Exception:
            logger.exception("Failed to generate AI reply for user %s", user_id)
            return translate("ai_unavailable", language)

    async def draft_reply(
        self, user_id: int, user_message: str, *, reply_context: str | None = None
    ) -> str | None:
        """Generate a reply draft without recording it to memory.

        Used in suggest mode — the owner receives the draft via DM and pastes it
        manually; the pasted message arrives as an owner-side business message and
        gets recorded through the normal sender_is_owner path.
        """

        if not self.enabled:
            return None

        language = self.settings_service.get_language(user_id)
        try:
            messages = await self._build_messages(
                user_id, user_message, language, reply_context=reply_context
            )
            reply = await complete_text(
                self.llm_service,
                messages,
                purpose="draft",
                contact_user_id=user_id,
                prompt_version=REPLY_PROMPT_VERSION,
                context_policy_version=CONTEXT_POLICY_VERSION,
            )
            if _contains_cjk(reply):
                reply = await self._rewrite_without_cjk(messages, reply, language)
            return _sanitize_reply(reply)
        except Exception:
            logger.exception("Failed to draft reply for user %s", user_id)
            return None

    async def preview_reply(
        self,
        user_id: int,
        user_message: str,
        *,
        system_prompt_override: str | None = None,
    ) -> dict[str, object]:
        """Dry-run reply — returns the assembled messages and reply without recording.

        Used by the admin prompt playground so the owner can tune personas without
        polluting the live conversation memory.
        """
        import time

        language = self.settings_service.get_language(user_id)
        compiled_context = await self._compile_context(user_id, user_message, language)
        messages = self._messages_from_context(compiled_context, user_id, user_message, language)
        if system_prompt_override is not None:
            messages[0] = {"role": "system", "content": system_prompt_override}
        t0 = time.monotonic()
        try:
            reply = _sanitize_reply(
                await complete_text(
                    self.llm_service,
                    messages,
                    purpose="preview",
                    contact_user_id=user_id,
                    prompt_version=REPLY_PROMPT_VERSION,
                    context_policy_version=CONTEXT_POLICY_VERSION,
                )
            )
        except Exception:
            logger.exception("Preview reply failed for user %s", user_id)
            reply = translate("ai_unavailable", language)
        latency_ms = round((time.monotonic() - t0) * 1000)
        return {
            "reply": reply,
            "assembled_messages": messages,
            "context_blocks": [
                {
                    "kind": decision.block.kind,
                    "priority": decision.block.priority,
                    "confidence": decision.block.confidence,
                    "source_id": decision.block.source_id,
                    "freshness_at": (
                        decision.block.freshness_at.isoformat()
                        if decision.block.freshness_at is not None
                        else None
                    ),
                    "sensitivity": decision.block.sensitivity,
                    "estimated_tokens": decision.block.estimated_tokens,
                    "placement": decision.block.placement,
                    "included": decision.included,
                    "inclusion_reason": decision.reason,
                }
                for decision in compiled_context.decisions
            ],
            "context_estimated_tokens": compiled_context.estimated_tokens,
            "context_considered_tokens": compiled_context.considered_tokens,
            "prompt_version": REPLY_PROMPT_VERSION,
            "context_policy_version": CONTEXT_POLICY_VERSION,
            "latency_ms": latency_ms,
        }

    async def _build_messages(
        self,
        user_id: int,
        user_message: str,
        language: str,
        *,
        reply_context: str | None = None,
    ) -> list[dict[str, str]]:
        compiled_context = await self._compile_context(
            user_id, user_message, language, reply_context=reply_context
        )
        return self._messages_from_context(
            compiled_context, user_id, user_message, language, reply_context=reply_context
        )

    def _messages_from_context(
        self,
        compiled_context: CompiledContext,
        user_id: int,
        user_message: str,
        language: str,
        *,
        reply_context: str | None = None,
    ) -> list[dict[str, str]]:
        """Combine compiled system context with the existing live message window."""

        messages: list[dict[str, str]] = [
            {"role": "system", "content": compiled_context.system_prompt}
        ]
        messages.extend(compiled_context.live_messages)
        messages.append(
            {
                "role": "user",
                "content": _current_user_content(
                    user_message, compiled_context.reply_context, language
                ),
            }
        )
        return messages

    async def _compile_context(
        self,
        user_id: int,
        user_message: str,
        language: str,
        *,
        reply_context: str | None = None,
    ) -> CompiledContext:
        """Assemble typed source blocks for the reply system prompt (Phase 20A)."""

        profile = self.profile_service.get_or_create_profile(user_id)
        mood = self.mood_service.latest_mood(user_id)
        summary = self.memory_service.get_summary(user_id)
        rag_context = ""
        if self.rag_service is not None:
            rag_context = await self.rag_service.retrieve_context(user_id, user_message)

        weather_context = ""
        if self.weather_service is not None and is_weather_query(user_message):
            weather_context = await self.weather_service.get_context(language) or ""

        blocks: list[ContextBlock] = [
            context_block(
                "persona",
                self.settings_service.resolve_persona_prompt(
                    user_id, language, profile.display_name
                ),
                priority=1000,
                source_id="resolved_persona",
                sensitivity="owner_private",
                required=True,
            )
        ]
        if mood is not None:
            blocks.append(
                context_block(
                    "mood",
                    (
                        f" Последнее настроение: {mood.mood}/5."
                        if language == "ru"
                        else f" Latest mood: {mood.mood}/5."
                    ),
                    priority=900,
                    source_id=f"mood:{getattr(mood, 'id', None) or user_id}",
                    freshness_at=_freshness_at(getattr(mood, "recorded_at", None)),
                    sensitivity="owner_private",
                )
            )
        if summary is not None:
            blocks.append(
                context_block(
                    "summary",
                    (
                        f" Краткое резюме разговора: {summary.summary}."
                        if language == "ru"
                        else f" Conversation summary: {summary.summary}."
                    ),
                    priority=800,
                    source_id=f"summary:{user_id}",
                    freshness_at=_freshness_at(getattr(summary, "updated_at", None)),
                )
            )
        if self.recall_service is not None:
            recall_context = await self.recall_service.retrieve(
                user_id, user_message, exclude_recent_n=self.memory_service.window_size
            )
            if recall_context:
                blocks.append(
                    context_block(
                        "recall",
                        (
                            f" Из прошлых разговоров: {recall_context}."
                            if language == "ru"
                            else f" From past conversations: {recall_context}."
                        ),
                        priority=700,
                        source_id=f"semantic_recall:{user_id}",
                    )
                )
        if self.facts_service is not None:
            facts = self.facts_service.get_facts(user_id)
            labels = self.facts_service._label_map(language)
            for fact in facts:
                label = labels.get(fact.key, fact.key)
                blocks.append(
                    context_block(
                        "fact",
                        (
                            f" Известный факт о контакте: {label}={fact.value}."
                            if language == "ru"
                            else f" Known fact about this contact: {label}={fact.value}."
                        ),
                        priority=600,
                        source_id=fact.version_id or f"contact_fact:{user_id}:{fact.key}",
                        confidence=fact.confidence,
                        freshness_at=fact.last_observed_at,
                        conflict_key=f"contact_fact:{fact.key}",
                    )
                )
        if rag_context:
            blocks.append(
                context_block(
                    "rag",
                    (
                        f" Заметки: {rag_context}."
                        if language == "ru"
                        else f" Relevant notes: {rag_context}."
                    ),
                    priority=500,
                    source_id=f"rag:{user_id}",
                )
            )
        if weather_context:
            blocks.append(
                context_block(
                    "weather",
                    f" {weather_context}",
                    priority=400,
                    source_id="weather",
                    sensitivity="external",
                )
            )

        openness = self.settings_service.get_openness(user_id)
        settings = self.settings_service.get_user_settings(user_id)

        # Owner-style mimicry: only when opted in for this contact AND the contact
        # is not on a reserved footing (reserved = don't reveal the real you).
        if settings.style_learning_enabled and openness != "reserved":
            contact_style = self.memory_service.get_style_profile(user_id)
            global_style = self.memory_service.get_owner_style_profile("global")
            relationship_scope = _relationship_style_scope(settings)
            relationship_style = (
                self.memory_service.get_owner_style_profile(relationship_scope)
                if relationship_scope
                else None
            )
            if any(
                style is not None and style.profile
                for style in (global_style, relationship_style, contact_style)
            ):
                blocks.append(
                    context_block(
                        "style",
                        " "
                        + _style_layers_prompt(
                            language,
                            global_profile=global_style.profile if global_style else None,
                            relationship_profile=(
                                relationship_style.profile if relationship_style else None
                            ),
                            contact_profile=contact_style.profile if contact_style else None,
                        ),
                        priority=300,
                        source_id=f"style_layers:{relationship_scope or 'none'}:{user_id}",
                        freshness_at=_freshness_at(
                            getattr(contact_style or relationship_style or global_style, "updated_at", None)
                        ),
                        sensitivity="owner_private",
                    )
                )

        # Curated few-shot examples remain before accuracy and openness policy so
        # their influence cannot override those safety-oriented instructions.
        if self.examples_service is not None:
            examples_block = self.examples_service.examples_block(
                user_id, language, query=user_message
            )
            if examples_block:
                blocks.append(
                    context_block(
                        "examples",
                        examples_block,
                        priority=200,
                        source_id=f"contact_examples:{user_id}",
                        sensitivity="owner_private",
                    )
                )

        if self.learning_proposals_service is not None:
            rules_block = self.learning_proposals_service.approved_rules_block(user_id, language)
            if rules_block:
                blocks.append(
                    context_block(
                        "owner_rules",
                        rules_block,
                        priority=250,
                        source_id=f"learning_proposals:{user_id}",
                        sensitivity="owner_private",
                    )
                )

        blocks.extend(
            [
                context_block(
                    "accuracy_policy",
                    _accuracy_directive(language),
                    priority=100,
                    required=True,
                ),
                context_block(
                    "openness_policy",
                    _openness_directive(openness, language),
                    priority=0,
                    source_id=f"openness:{user_id}",
                    sensitivity="policy",
                    required=True,
                ),
            ]
        )
        live_messages = tuple(self.memory_service.as_chat_messages(user_id))
        if live_messages:
            live_content = "\n".join(
                f"{message['role']}: {message['content']}" for message in live_messages
            )
            blocks.append(
                context_block(
                    "live_window",
                    live_content,
                    priority=850,
                    source_id=f"live_window:{user_id}",
                    placement="live_window",
                )
            )
        if reply_context:
            blocks.append(
                context_block(
                    "quoted_message",
                    reply_context,
                    priority=950,
                    source_id="reply_context",
                    placement="quoted_message",
                )
            )
        compiled = self.context_compiler.compile(blocks)
        included_kinds = {block.kind for block in compiled.blocks}
        return CompiledContext(
            system_prompt=compiled.system_prompt,
            blocks=compiled.blocks,
            estimated_tokens=compiled.estimated_tokens,
            live_messages=live_messages if "live_window" in included_kinds else (),
            reply_context=reply_context if "quoted_message" in included_kinds else None,
            decisions=compiled.decisions,
            considered_tokens=compiled.considered_tokens,
        )

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
            rewritten = await complete_text(
                self.llm_service,
                retry_messages,
                purpose="reply",
                contact_user_id=None,
                prompt_version=REPLY_PROMPT_VERSION,
                context_policy_version=CONTEXT_POLICY_VERSION,
            )
            if not _contains_cjk(rewritten):
                return rewritten
            logger.warning(
                "LLM still returned CJK characters after rewrite for language %s", language
            )
        except Exception:
            logger.exception("Failed to rewrite mixed-language reply for language %s", language)
        return reply

    async def transcribe_voice(self, provider: object, audio_bytes: bytes) -> str:
        """Transcribe a voice message using the configured provider."""

        if hasattr(provider, "transcribe"):
            return await provider.transcribe(audio_bytes)
        raise RuntimeError("Configured LLM provider does not support transcription.")
