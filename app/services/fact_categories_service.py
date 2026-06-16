"""Global custom fact categories — owner-defined keys for contact facts.

Built-in keys (KNOWN_KEYS in contact_facts_service) are always available.
Custom categories add owner-defined keys that the LLM will also try to
extract automatically from conversation context.
"""

from __future__ import annotations

import re

from app.database.repositories.fact_categories import FactCategoriesRepository

_SLUG_RE = re.compile(r"^[a-z0-9_]{1,30}$")


class FactCategoriesService:
    """Manage global custom fact categories."""

    def __init__(self, repository: FactCategoriesRepository) -> None:
        self.repository = repository

    def list_categories(self) -> list[dict[str, str]]:
        """Return all custom categories as list of {key, label} dicts."""
        return self.repository.list_categories()

    def list_keys(self) -> set[str]:
        """Return the set of all custom category keys."""
        return {c["key"] for c in self.repository.list_categories()}

    def add_category(self, key: str, label: str) -> None:
        key = key.strip().lower()
        label = label.strip()
        if not _SLUG_RE.match(key):
            raise ValueError(
                f"Category key must be lowercase letters, digits or underscores, "
                f"1–30 chars (got {key!r})"
            )
        if not label:
            raise ValueError("Category label is required.")
        if len(label) > 80:
            raise ValueError("Category label must be ≤ 80 characters.")
        self.repository.add_category(key, label)

    def delete_category(self, key: str) -> None:
        self.repository.delete_category(key)
