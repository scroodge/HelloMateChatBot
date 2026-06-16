"""Global custom fact categories — owner-defined keys for contact facts.

Built-in keys (KNOWN_KEYS in contact_facts_service) are always available.
Custom categories add owner-defined keys that the LLM will also try to
extract automatically from conversation context.

A category can be single-valued (one value per contact, e.g. a custom
"nickname") or multi-valued (a list, e.g. "любимое" / favorites).

The owner only types a human-readable label (e.g. "Любимая еда"); the
machine key (a slug used in storage and the LLM prompt) is derived
automatically by transliterating + slugifying that label.
"""

from __future__ import annotations

import re

from app.database.repositories.fact_categories import FactCategoriesRepository

_SLUG_RE = re.compile(r"^[a-z0-9_]{1,30}$")

# Cyrillic → Latin transliteration so a Russian label yields a clean ASCII slug.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _slugify(text: str) -> str:
    """Turn a human label into a snake_case ASCII slug (≤ 30 chars)."""
    out: list[str] = []
    for ch in text.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isascii() and ch.isalnum():
            out.append(ch)
        else:
            out.append(" ")
    slug = "_".join("".join(out).split())
    return slug[:30].strip("_")


class FactCategoriesService:
    """Manage global custom fact categories."""

    def __init__(self, repository: FactCategoriesRepository) -> None:
        self.repository = repository

    def list_categories(self) -> list[dict[str, object]]:
        """Return all custom categories as list of {key, label, multi} dicts."""
        return self.repository.list_categories()

    def list_keys(self) -> set[str]:
        """Return the set of all custom category keys."""
        return {str(c["key"]) for c in self.repository.list_categories()}

    def multi_keys(self) -> set[str]:
        """Return the set of custom category keys that hold multiple values."""
        return {str(c["key"]) for c in self.repository.list_categories() if c.get("multi")}

    def _unique_key(self, base: str) -> str:
        """Append a numeric suffix if the slug already exists."""
        existing = self.list_keys()
        if base not in existing:
            return base
        i = 2
        while f"{base[:27]}_{i}" in existing:
            i += 1
        return f"{base[:27]}_{i}"

    def add_category(self, label: str, multi: bool = False, key: str | None = None) -> str:
        """Add a category from a human label; the key is auto-derived if omitted.

        Returns the final (possibly auto-generated, uniqueness-suffixed) key.
        """
        label = label.strip()
        if not label:
            raise ValueError("Укажите название категории.")
        if len(label) > 80:
            raise ValueError("Название категории должно быть ≤ 80 символов.")

        key = (key or "").strip().lower()
        if not key:
            key = _slugify(label) or f"cat_{abs(hash(label)) % 100000}"
        if not _SLUG_RE.match(key):
            raise ValueError(
                "Ключ должен состоять из латинских букв, цифр или подчёркиваний "
                f"(1–30 символов), получено {key!r}"
            )

        key = self._unique_key(key)
        self.repository.add_category(key, label, multi)
        return key

    def delete_category(self, key: str) -> None:
        self.repository.delete_category(key)
