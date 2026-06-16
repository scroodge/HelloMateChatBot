"""Per-contact durable facts — Phase 11.

Extracts stable facts (name, city, occupation, birthday, interests…) from
recent conversation messages using the LLM, persists them as key-value pairs
per contact, and makes them available to the reply prompt.  Extraction is
fire-and-forget, runs in the background, and is throttled by
facts_refresh_interval so it only re-fires when enough new messages have
arrived since the last extraction.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from app.database.repositories.facts import ContactFactsRepository
from app.models.facts import ContactFact
from app.services.llm import LLMService
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Keys the LLM is allowed to return; unknown keys are ignored.
KNOWN_KEYS = {
    "name",
    "age",
    "birthday",
    "city",
    "country",
    "occupation",
    "workplace",
    "interests",
    "relationship",
    "family",
    "language",
    "notes",
}

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_facts_json(raw: str, allowed_keys: frozenset[str]) -> dict[str, str]:
    """Extract a JSON object from the LLM response, tolerating markdown fences."""
    text = raw.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract the first {...} block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
        else:
            return {}
    if not isinstance(data, dict):
        return {}
    return {
        k: str(v).strip()
        for k, v in data.items()
        if isinstance(k, str) and k in allowed_keys and v and str(v).strip()
    }


def _build_extraction_messages(
    recent_messages: list[dict[str, str]],
    existing_facts: dict[str, str],
    language: str,
    extra_keys: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Build LLM prompt for fact extraction.

    extra_keys: list of (key, label) for owner-defined custom categories.
    They are appended to keys_hint so the LLM knows to extract them too.
    """

    builtin_hint = (
        "name, age, birthday, city, country, occupation, workplace, "
        "interests, relationship, family, language, notes"
    )
    if extra_keys:
        custom_hint = ", ".join(f"{k} ({lbl})" for k, lbl in extra_keys)
        keys_hint = f"{builtin_hint}, {custom_hint}"
    else:
        keys_hint = builtin_hint

    if language == "ru":
        system = (
            "Ты извлекаешь устойчивые факты о собеседнике из переписки. "
            "Возвращай ТОЛЬКО валидный JSON-объект без пояснений. "
            f"Допустимые ключи: {keys_hint}. "
            "Включай только факты, которые явно следуют из переписки. "
            "Не придумывай. Значения — короткие строки на русском. "
            "Если факт уже известен и не изменился — повтори его. "
            "Если нового ничего нет — верни пустой объект {{}}."
        )
        intro_existing = "Уже известные факты:" if existing_facts else ""
        intro_chat = "Последние сообщения (Я / Контакт):"
        ask = "Верни JSON с фактами о Контакте."
        owner_label, contact_label = "Я", "Контакт"
    else:
        system = (
            "You extract stable personal facts about the contact from a chat. "
            "Return ONLY a valid JSON object with no explanation. "
            f"Allowed keys: {keys_hint}. "
            "Only include facts clearly stated in the conversation. "
            "Do not invent. Values should be short strings. "
            "If a fact is already known and unchanged — repeat it. "
            "If nothing new — return an empty object {{}}."
        )
        intro_existing = "Already known facts:" if existing_facts else ""
        intro_chat = "Recent messages (Me / Contact):"
        ask = "Return JSON with facts about the Contact."
        owner_label, contact_label = "Me", "Contact"

    lines: list[str] = []
    if intro_existing:
        lines.append(intro_existing)
        lines.append(json.dumps(existing_facts, ensure_ascii=False))
        lines.append("")
    lines.append(intro_chat)
    for m in recent_messages:
        who = owner_label if m["role"] == "assistant" else contact_label
        lines.append(f"{who}: {m['content']}")
    lines.append("")
    lines.append(ask)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(lines)},
    ]


class ContactFactsService:
    """Extract and store durable facts about contacts."""

    def __init__(
        self,
        *,
        repository: ContactFactsRepository,
        memory_service: MemoryService,
        llm_service: LLMService,
        settings_service: SettingsService,
        refresh_interval: int,
        enabled: bool,
        categories_service=None,
    ) -> None:
        self.repository = repository
        self.memory_service = memory_service
        self.llm_service = llm_service
        self.settings_service = settings_service
        self.refresh_interval = max(1, refresh_interval)
        self.enabled = enabled
        self.categories_service = categories_service
        self._in_progress: set[int] = set()
        self._tasks: set[asyncio.Task[None]] = set()

    def _allowed_keys(self) -> frozenset[str]:
        """Return the union of built-in and owner-defined custom keys."""
        custom = self.categories_service.list_keys() if self.categories_service else set()
        return frozenset(KNOWN_KEYS | custom)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_facts(self, user_id: int) -> list[ContactFact]:
        return self.repository.get_facts(user_id)

    def facts_as_dict(self, user_id: int) -> dict[str, str]:
        return {f.key: f.value for f in self.get_facts(user_id)}

    def set_fact(self, user_id: int, key: str, value: str) -> None:
        allowed = self._allowed_keys()
        if key not in allowed:
            raise ValueError(f"Unknown fact key: {key!r}. Allowed: {sorted(allowed)}")
        self.repository.set_fact(user_id, key, value)

    def delete_fact(self, user_id: int, key: str) -> None:
        self.repository.delete_fact(user_id, key)

    def clear_facts(self, user_id: int) -> None:
        self.repository.clear_facts(user_id)

    def schedule_extraction(self, user_id: int) -> None:
        """Fire-and-forget fact extraction on the running event loop."""
        if not self.enabled:
            return
        try:
            task = asyncio.create_task(self.maybe_extract(user_id))
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def maybe_extract(self, user_id: int) -> None:
        """Extract facts if enough new messages have arrived since last extraction."""
        if not self.enabled or user_id in self._in_progress:
            return

        total = self.memory_service.count_messages(user_id)
        meta = self.repository.get_meta(user_id)
        last_count = meta.last_message_count if meta else 0
        delta = total - last_count
        if delta < self.refresh_interval:
            return

        self._in_progress.add(user_id)
        try:
            await self._do_extract(user_id, total)
        except Exception:
            logger.exception("Failed to extract facts for contact %s", user_id)
        finally:
            self._in_progress.discard(user_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _do_extract(self, user_id: int, total: int) -> None:
        recent = self.memory_service.recent_messages(user_id)
        if not recent:
            return

        existing = self.facts_as_dict(user_id)
        language = self.settings_service.get_language(user_id)
        extra_categories = (
            [(c["key"], c["label"]) for c in self.categories_service.list_categories()]
            if self.categories_service
            else None
        )
        allowed_keys = self._allowed_keys()
        prompt = _build_extraction_messages(
            [{"role": m.role, "content": m.content} for m in recent],
            existing,
            language,
            extra_keys=extra_categories,
        )
        raw = (await self.llm_service.complete(prompt)).strip()
        new_facts = _parse_facts_json(raw, allowed_keys)

        # Merge: update known keys, never delete previously extracted ones
        for key, value in new_facts.items():
            self.repository.set_fact(user_id, key, value)

        self.repository.set_meta(user_id, total)
        logger.info(
            "Facts extracted for contact %s: %d facts, %d updated",
            user_id,
            len(self.facts_as_dict(user_id)),
            len(new_facts),
        )
