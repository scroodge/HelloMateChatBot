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

# Built-in keys that hold a list of values (the LLM appends, the owner manages
# items individually). Atomic keys (name, birthday, …) stay single-valued.
MULTI_BUILTIN_KEYS = {"interests", "family"}

# Human-readable labels for the built-in keys, per language. Used both for the
# Mini App and for the reply prompt (the model reads the label, not the slug).
BUILTIN_LABELS = {
    "ru": {
        "name": "Имя",
        "age": "Возраст",
        "birthday": "День рождения",
        "city": "Город",
        "country": "Страна",
        "occupation": "Профессия",
        "workplace": "Работа",
        "interests": "Интересы",
        "relationship": "Отношения",
        "family": "Семья",
        "language": "Язык",
        "notes": "Заметки",
    },
    "en": {
        "name": "Name",
        "age": "Age",
        "birthday": "Birthday",
        "city": "City",
        "country": "Country",
        "occupation": "Occupation",
        "workplace": "Workplace",
        "interests": "Interests",
        "relationship": "Relationship",
        "family": "Family",
        "language": "Language",
        "notes": "Notes",
    },
}

# Hard cap on how many values a multi-valued fact may accumulate.
MAX_FACT_VALUES = 15

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _decode_values(raw: str) -> list[str]:
    """Decode a stored multi-valued fact into a list.

    New rows store a JSON array; legacy rows store a comma-separated string.
    Both are handled so existing data keeps working after the upgrade.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(v).strip() for v in data if str(v).strip()]
        except json.JSONDecodeError:
            pass
    # Legacy / plain: split on commas.
    return [part.strip() for part in raw.split(",") if part.strip()]


def _encode_values(values: list[str]) -> str:
    """Encode a list of values for storage as a JSON array string."""
    return json.dumps(values, ensure_ascii=False)


def _dedup(values: list[str]) -> list[str]:
    """Drop case-insensitive duplicates, preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        v = v.strip()
        if not v:
            continue
        low = v.casefold()
        if low in seen:
            continue
        seen.add(low)
        out.append(v)
    return out


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
    multi_keys: set[str] | None = None,
) -> list[dict[str, str]]:
    """Build LLM prompt for fact extraction.

    extra_keys: list of (key, label) for owner-defined custom categories.
    They are appended to keys_hint so the LLM knows to extract them too.
    multi_keys: keys that may hold several values (the model should return them
    comma-separated within the string value for that key).
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

    multi_list = sorted(multi_keys) if multi_keys else []
    multi_hint_ru = (
        f" Ключи {', '.join(multi_list)} могут содержать несколько значений — "
        "перечисли их через запятую в одной строке."
        if multi_list
        else ""
    )
    multi_hint_en = (
        f" Keys {', '.join(multi_list)} may hold several values — "
        "list them comma-separated in a single string."
        if multi_list
        else ""
    )

    if language == "ru":
        system = (
            "Ты извлекаешь устойчивые факты о собеседнике из переписки. "
            "Возвращай ТОЛЬКО валидный JSON-объект без пояснений. "
            f"Допустимые ключи: {keys_hint}.{multi_hint_ru} "
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
            f"Allowed keys: {keys_hint}.{multi_hint_en} "
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

    def _multi_keys(self) -> frozenset[str]:
        """Return all keys (built-in + custom) that hold a list of values."""
        custom = self.categories_service.multi_keys() if self.categories_service else set()
        return frozenset(MULTI_BUILTIN_KEYS | custom)

    def is_multi(self, key: str) -> bool:
        return key in self._multi_keys()

    def _label_map(self, language: str) -> dict[str, str]:
        """key -> human label, merging built-in (localized) and custom labels."""
        labels = dict(BUILTIN_LABELS.get(language, BUILTIN_LABELS["en"]))
        if self.categories_service:
            for c in self.categories_service.list_categories():
                labels[str(c["key"])] = str(c["label"])
        return labels

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_facts(self, user_id: int) -> list[ContactFact]:
        return self.repository.get_facts(user_id)

    def facts_as_dict(self, user_id: int) -> dict[str, str]:
        """Facts as flat key->string, with multi-valued lists joined by ', '.

        Used for prompt injection where a readable single line per key is wanted.
        """
        multi = self._multi_keys()
        out: dict[str, str] = {}
        for f in self.get_facts(user_id):
            if f.key in multi:
                out[f.key] = ", ".join(_decode_values(f.value))
            else:
                out[f.key] = f.value
        return out

    def facts_structured(self, user_id: int) -> dict[str, dict[str, object]]:
        """Facts as key -> {multi, values, label}. Used by the API/UI to render chips."""
        multi = self._multi_keys()
        try:
            language = self.settings_service.get_language(user_id)
        except Exception:
            language = "ru"
        labels = self._label_map(language)
        out: dict[str, dict[str, object]] = {}
        for f in self.get_facts(user_id):
            label = labels.get(f.key, f.key)
            if f.key in multi:
                out[f.key] = {"multi": True, "values": _decode_values(f.value), "label": label}
            else:
                out[f.key] = {"multi": False, "values": [f.value], "label": label}
        return out

    def facts_for_prompt(self, user_id: int, language: str) -> dict[str, str]:
        """Facts as human-label -> value string, for injection into the reply prompt.

        The model reads the label (e.g. "Любимая еда"), never the raw slug
        (e.g. "lyubimaya_eda"), which it would otherwise have to decode.
        """
        labels = self._label_map(language)
        return {labels.get(k, k): v for k, v in self.facts_as_dict(user_id).items()}

    def set_fact(self, user_id: int, key: str, value: str) -> None:
        """Set (single) or append (multi) a fact value.

        For multi keys, value may itself be comma-separated; all items are merged
        into the existing list (deduped, capped). For single keys the value
        overwrites.
        """
        allowed = self._allowed_keys()
        if key not in allowed:
            raise ValueError(f"Unknown fact key: {key!r}. Allowed: {sorted(allowed)}")

        if key in self._multi_keys():
            existing = self._current_values(user_id, key)
            if "," in value or value.strip().startswith("["):
                incoming = _decode_values(value)
            else:
                incoming = [value]
            merged = _dedup(existing + incoming)[:MAX_FACT_VALUES]
            if merged:
                self.repository.set_fact(user_id, key, _encode_values(merged))
            else:
                self.repository.delete_fact(user_id, key)
        else:
            self.repository.set_fact(user_id, key, value)

    def remove_fact_value(self, user_id: int, key: str, value: str) -> None:
        """Remove a single value from a multi-valued fact (no-op for single keys).

        If the last value is removed, the whole key is deleted.
        """
        if key not in self._multi_keys():
            # Single-valued: removing "the value" just deletes the fact.
            self.repository.delete_fact(user_id, key)
            return
        remaining = [
            v for v in self._current_values(user_id, key) if v.casefold() != value.casefold()
        ]
        if remaining:
            self.repository.set_fact(user_id, key, _encode_values(remaining))
        else:
            self.repository.delete_fact(user_id, key)

    def _current_values(self, user_id: int, key: str) -> list[str]:
        for f in self.get_facts(user_id):
            if f.key == key:
                return _decode_values(f.value)
        return []

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
            [(str(c["key"]), str(c["label"])) for c in self.categories_service.list_categories()]
            if self.categories_service
            else None
        )
        allowed_keys = self._allowed_keys()
        multi_keys = set(self._multi_keys())
        prompt = _build_extraction_messages(
            [{"role": m.role, "content": m.content} for m in recent],
            existing,
            language,
            extra_keys=extra_categories,
            multi_keys=multi_keys,
        )
        raw = (await self.llm_service.complete(prompt)).strip()
        new_facts = _parse_facts_json(raw, allowed_keys)

        # Merge: set_fact overwrites single keys and appends+dedups multi keys.
        for key, value in new_facts.items():
            self.set_fact(user_id, key, value)

        self.repository.set_meta(user_id, total)
        logger.info(
            "Facts extracted for contact %s: %d facts, %d updated",
            user_id,
            len(self.facts_as_dict(user_id)),
            len(new_facts),
        )
