"""Rolling conversation summary (Phase 10).

Keeps a per-contact running summary of everything older than the live message
window, so the bot retains context beyond the last N messages without growing
the prompt. The summary is refreshed incrementally in the background: each
refresh folds only the messages that have aged out of the window since the
previous refresh into the existing summary.
"""

from __future__ import annotations

import asyncio
import logging

from app.services.llm import LLMService, complete_text
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

REBUILD_BATCH_SIZE = 100


def _truncate_summary(text: str, max_chars: int) -> str:
    """Fit a summary without leaving a dangling partial sentence or word."""

    text = text.strip()
    if len(text) <= max_chars:
        return text

    clipped = text[:max_chars]
    boundaries = [clipped.rfind(mark) for mark in (". ", "! ", "? ", "\n")]
    boundary = max(boundaries)
    if boundary >= max_chars // 2:
        ending = clipped[boundary]
        return clipped[: boundary + (0 if ending == "\n" else 1)].rstrip()

    word_boundary = clipped.rfind(" ")
    if word_boundary > 0:
        return clipped[:word_boundary].rstrip(" ,;:-—") + "…"
    return clipped


def _build_summary_messages(
    existing_summary: str | None,
    new_messages: list[dict[str, str]],
    language: str,
    max_chars: int,
) -> list[dict[str, str]]:
    """Build the LLM prompt that folds new messages into the running summary."""

    if language == "ru":
        system = (
            "Ты ведёшь сжатую смысловую сводку личной переписки для будущих ответов. "
            "Сохраняй только значимые темы, явно высказанные факты, договорённости, "
            "планы, границы, повторяющиеся шутки и текущую эмоциональную динамику. "
            "Не сохраняй приветствия, реакции, погоду, спорт, счёты, ссылки и разовые "
            "бытовые детали, если они не стали договорённостью, планом или повторяющейся "
            "темой. Всегда различай стороны: 'Контакт' — другая сторона переписки, "
            "'Я' — владелец аккаунта. "
            "Ясно указывай, кто что сказал, предложил, любит или планирует; не переноси "
            "слова и свойства одной стороны на другую. Не превращай сводку в стенограмму, "
            "не перечисляй отдельные реплики и не сохраняй бессвязные короткие фразы. "
            "Не делай выводов о родстве, отношениях, чувствах или намерениях, если они "
            "не были прямо сформулированы. При неоднозначности опусти деталь. "
            "Пиши не больше пяти связных коротких предложений по-русски, без преамбулы "
            f"и обращения к читателю — только сама сводка, не длиннее ~{max_chars} символов."
        )
        intro_prev = "Текущая сводка:"
        intro_new = "Новые сообщения, которые нужно добавить в сводку (Контакт / Я):"
        ask = "Верни обновлённую единую сводку."
        owner_label, contact_label = "Я", "Контакт"
    else:
        system = (
            "You maintain a compact semantic summary of a private chat for future replies. "
            "Keep only meaningful topics, explicitly stated facts, agreements, plans, "
            "boundaries, recurring jokes, and the current emotional dynamic. Always "
            "Discard greetings, reactions, weather, sports, scores, links, and one-off "
            "everyday details unless they became an agreement, plan, or recurring topic. "
            "distinguish the parties: 'Contact' is the correspondent and 'Me' is the "
            "account owner. State clearly who said, proposed, likes, or plans each thing; "
            "never transfer words or attributes from one party to the other. Do not write "
            "a transcript, list isolated messages, or preserve disconnected fragments. "
            "Do not infer family ties, relationships, feelings, or intentions unless they "
            "were stated explicitly. Omit ambiguous details. Use no more than five short "
            f"connected sentences, with no preamble or reader address, at most ~{max_chars} characters."
        )
        intro_prev = "Current summary:"
        intro_new = "New messages to fold into the summary (Contact / Me):"
        ask = "Return the updated single summary."
        owner_label, contact_label = "Me", "Contact"

    lines: list[str] = []
    if existing_summary:
        lines.append(f"{intro_prev}\n{existing_summary}\n")
    lines.append(intro_new)
    for m in new_messages:
        who = owner_label if m["role"] == "assistant" else contact_label
        lines.append(f"{who}: {m['content']}")
    lines.append("")
    lines.append(ask)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(lines)},
    ]


class SummaryService:
    """Maintain an incremental rolling summary per contact."""

    def __init__(
        self,
        *,
        memory_service: MemoryService,
        llm_service: LLMService,
        settings_service: SettingsService,
        window_size: int,
        refresh_interval: int,
        max_chars: int,
        enabled: bool,
    ) -> None:
        self.memory_service = memory_service
        self.llm_service = llm_service
        self.settings_service = settings_service
        self.window_size = window_size
        self.refresh_interval = max(1, refresh_interval)
        self.max_chars = max_chars
        self.enabled = enabled
        self._in_progress: set[int] = set()
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule_refresh(self, user_id: int) -> None:
        """Fire-and-forget a summary refresh on the running event loop.

        Keeps a strong reference to the task so it is not garbage-collected
        mid-flight, and never cancels it.
        """
        if not self.enabled:
            return
        try:
            task = asyncio.create_task(self.maybe_refresh(user_id))
        except RuntimeError:
            # No running loop (e.g. called from sync context) — skip silently.
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def maybe_refresh(self, user_id: int) -> None:
        """Refresh the summary if enough messages have aged out of the window."""

        if not self.enabled or user_id in self._in_progress:
            return

        total = self.memory_service.count_messages(user_id)
        if total <= self.window_size:
            return  # everything still fits in the live window

        num_older = total - self.window_size
        existing = self.memory_service.get_summary(user_id)
        covered = existing.covered_count if existing else 0
        delta = num_older - covered
        if delta < self.refresh_interval:
            return  # not enough new aged-out messages yet

        self._in_progress.add(user_id)
        try:
            new_messages = self.memory_service.messages_slice(user_id, offset=covered, limit=delta)
            if not new_messages:
                return
            language = self.settings_service.get_language(user_id)
            prompt = _build_summary_messages(
                existing.summary if existing else None,
                [{"role": m.role, "content": m.content} for m in new_messages],
                language,
                self.max_chars,
            )
            summary = (
                await complete_text(
                    self.llm_service, prompt, purpose="summary", contact_user_id=user_id
                )
            ).strip()
            if not summary:
                return
            self.memory_service.set_summary(
                user_id, _truncate_summary(summary, self.max_chars), covered_count=num_older
            )
            logger.info("Summary refreshed for contact %s (covered %d msgs)", user_id, num_older)
        except Exception:
            logger.exception("Failed to refresh summary for contact %s", user_id)
        finally:
            self._in_progress.discard(user_id)

    async def rebuild(self, user_id: int) -> str | None:
        """Recreate the derived summary from history without deleting messages.

        Old messages are folded in bounded chronological batches so a long chat
        never becomes one oversized LLM request.
        """

        if not self.enabled:
            return None
        if user_id in self._in_progress:
            raise RuntimeError("Summary refresh is already in progress")

        self._in_progress.add(user_id)
        try:
            self.memory_service.delete_summary(user_id)
            total = self.memory_service.count_messages(user_id)
            num_older = max(0, total - self.window_size)
            if num_older == 0:
                return None

            language = self.settings_service.get_language(user_id)
            covered = 0
            summary: str | None = None
            while covered < num_older:
                batch_size = min(REBUILD_BATCH_SIZE, num_older - covered)
                messages = self.memory_service.messages_slice(
                    user_id, offset=covered, limit=batch_size
                )
                if not messages:
                    break
                prompt = _build_summary_messages(
                    summary,
                    [{"role": m.role, "content": m.content} for m in messages],
                    language,
                    self.max_chars,
                )
                rebuilt = (
                    await complete_text(
                        self.llm_service, prompt, purpose="summary", contact_user_id=user_id
                    )
                ).strip()
                if not rebuilt:
                    raise RuntimeError("LLM returned an empty summary")
                summary = _truncate_summary(rebuilt, self.max_chars)
                covered += len(messages)
                self.memory_service.set_summary(user_id, summary, covered_count=covered)

            logger.info("Summary rebuilt for contact %s (covered %d msgs)", user_id, covered)
            return summary
        finally:
            self._in_progress.discard(user_id)
