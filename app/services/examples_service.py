"""Per-contact few-shot examples — curated (message -> ideal reply) pairs.

Unlike facts/summary/style, this is a purely manual, owner-curated signal: no
LLM extraction, no background jobs. The owner saves a handful of ideal replies
(e.g. from the Playground) and they are injected into the prompt as a few-shot
guide so the model copies the desired tone and format.
"""

from __future__ import annotations

import logging

from app.database.repositories.examples import ContactExamplesRepository
from app.models.examples import ContactExample

logger = logging.getLogger(__name__)

# Hard cap so the prompt never bloats. Few-shot benefit plateaus quickly; a
# handful of good examples is plenty and keeps latency/cost bounded.
MAX_EXAMPLES = 10

# Truncate each side so a single pasted wall of text can't dominate the prompt.
MAX_FIELD_CHARS = 600


class ContactExamplesService:
    """Store and serve curated few-shot examples per contact."""

    def __init__(self, repository: ContactExamplesRepository, *, enabled: bool = True) -> None:
        self.repository = repository
        self.enabled = enabled

    def list_examples(self, user_id: int) -> list[ContactExample]:
        return self.repository.list_examples(user_id)

    def add_example(self, user_id: int, contact_message: str, reply_text: str) -> ContactExample:
        contact_message = contact_message.strip()[:MAX_FIELD_CHARS]
        reply_text = reply_text.strip()[:MAX_FIELD_CHARS]
        if not contact_message or not reply_text:
            raise ValueError("Both contact_message and reply_text are required.")
        if self.repository.count_examples(user_id) >= MAX_EXAMPLES:
            raise ValueError(f"At most {MAX_EXAMPLES} examples per contact.")
        return self.repository.add_example(user_id, contact_message, reply_text)

    def delete_example(self, user_id: int, example_id: int) -> None:
        self.repository.delete_example(user_id, example_id)

    def clear_examples(self, user_id: int) -> None:
        self.repository.clear_examples(user_id)

    def global_stats(self) -> tuple[int, int]:
        """Return (total examples, number of contacts with examples)."""
        return self.repository.global_stats()

    def examples_block(self, user_id: int, language: str) -> str:
        """Return a system-prompt block of few-shot examples, or '' if none."""
        if not self.enabled:
            return ""
        examples = self.repository.list_examples(user_id)[:MAX_EXAMPLES]
        if not examples:
            return ""

        if language == "ru":
            header = (
                " Примеры идеальных ответов (повторяй их стиль, тон и длину, "
                "но не копируй дословно):"
            )
            contact_label, reply_label = "Контакт", "Ответ"
        else:
            header = (
                " Examples of ideal replies (mirror their style, tone and length, "
                "but do not copy verbatim):"
            )
            contact_label, reply_label = "Contact", "Reply"

        lines = [header]
        for i, ex in enumerate(examples, start=1):
            lines.append(
                f" {i}. {contact_label}: «{ex.contact_message}» — "
                f"{reply_label}: «{ex.reply_text}»"
            )
        return "".join(lines)
