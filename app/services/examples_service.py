"""Per-contact few-shot examples — curated (message -> reply) pairs.

Unlike facts/summary/style, this is a purely manual, owner-curated signal: no
LLM extraction, no background jobs. The owner saves a handful of ideal replies
(e.g. from the Playground) and they are injected into the prompt as a few-shot
guide so the model copies the desired tone and format.

Negative examples (kind='negative') are anti-patterns: the model is told to
avoid the tone and phrasing in those pairs.
"""

from __future__ import annotations

import logging
import re

from app.database.repositories.examples import ContactExamplesRepository
from app.models.examples import ContactExample

logger = logging.getLogger(__name__)

# Hard cap per kind so the prompt never bloats. Few-shot benefit plateaus
# quickly; a handful of good examples is plenty and keeps latency/cost bounded.
MAX_EXAMPLES = 10

# Truncate each side so a single pasted wall of text can't dominate the prompt.
MAX_FIELD_CHARS = 600
PROMPT_EXAMPLES_PER_KIND = 3

_VALID_KINDS = {"positive", "negative"}


class ContactExamplesService:
    """Store and serve curated few-shot examples per contact."""

    def __init__(self, repository: ContactExamplesRepository, *, enabled: bool = True) -> None:
        self.repository = repository
        self.enabled = enabled

    def list_examples(self, user_id: int) -> list[ContactExample]:
        return self.repository.list_examples(user_id)

    def add_example(
        self, user_id: int, contact_message: str, reply_text: str, kind: str = "positive"
    ) -> ContactExample:
        if kind not in _VALID_KINDS:
            raise ValueError(f"kind must be one of {_VALID_KINDS!r}, got {kind!r}.")
        contact_message = contact_message.strip()[:MAX_FIELD_CHARS]
        reply_text = reply_text.strip()[:MAX_FIELD_CHARS]
        if not contact_message or not reply_text:
            raise ValueError("Both contact_message and reply_text are required.")
        if self.repository.count_by_kind(user_id, kind) >= MAX_EXAMPLES:
            raise ValueError(f"At most {MAX_EXAMPLES} {kind} examples per contact.")
        return self.repository.add_example(user_id, contact_message, reply_text, kind)

    def delete_example(self, user_id: int, example_id: int) -> None:
        self.repository.delete_example(user_id, example_id)

    def clear_examples(self, user_id: int) -> None:
        self.repository.clear_examples(user_id)

    def global_stats(self) -> tuple[int, int]:
        """Return (total examples, number of contacts with examples)."""
        return self.repository.global_stats()

    def examples_block(self, user_id: int, language: str, *, query: str | None = None) -> str:
        """Return a system-prompt block of few-shot examples, or '' if none."""
        if not self.enabled:
            return ""
        all_examples = self.repository.list_examples(user_id)
        positives = [e for e in all_examples if e.kind == "positive"]
        negatives = [e for e in all_examples if e.kind == "negative"]
        if query:
            positives = self._rank_for_query(positives, query)[:PROMPT_EXAMPLES_PER_KIND]
            negatives = self._rank_for_query(negatives, query)[:PROMPT_EXAMPLES_PER_KIND]
        else:
            positives = positives[:MAX_EXAMPLES]
            negatives = negatives[:MAX_EXAMPLES]
        if not positives and not negatives:
            return ""

        if language == "ru":
            pos_header = (
                " Примеры идеальных ответов (повторяй их стиль, тон и длину, "
                "но не копируй дословно):"
            )
            neg_header = (
                " А так отвечать НЕ надо — избегай такого тона и формулировок:"
            )
            contact_label, reply_label = "Контакт", "Ответ"
            bad_reply_label = "Плохой ответ"
        else:
            pos_header = (
                " Examples of ideal replies (mirror their style, tone and length, "
                "but do not copy verbatim):"
            )
            neg_header = " Do NOT reply like this — avoid this tone and wording:"
            contact_label, reply_label = "Contact", "Reply"
            bad_reply_label = "Bad reply"

        parts: list[str] = []

        if positives:
            parts.append(pos_header)
            for i, ex in enumerate(positives, start=1):
                parts.append(
                    f" {i}. {contact_label}: «{ex.contact_message}» — "
                    f"{reply_label}: «{ex.reply_text}»"
                )

        if negatives:
            parts.append(neg_header)
            for i, ex in enumerate(negatives, start=1):
                parts.append(
                    f" {i}. {contact_label}: «{ex.contact_message}» — "
                    f"{bad_reply_label}: «{ex.reply_text}»"
                )

        return "".join(parts)

    @staticmethod
    def _rank_for_query(examples: list[ContactExample], query: str) -> list[ContactExample]:
        """Rank curated examples by lexical overlap, keeping stable ties deterministic."""

        query_terms = set(re.findall(r"\w+", query.casefold(), re.UNICODE))

        def score(example: ContactExample) -> tuple[int, int]:
            example_terms = set(re.findall(r"\w+", example.contact_message.casefold(), re.UNICODE))
            return len(query_terms & example_terms), example.id or 0

        ranked = sorted(examples, key=score, reverse=True)
        if ranked and score(ranked[0])[0] > 0:
            return [example for example in ranked if score(example)[0] > 0]
        return examples
