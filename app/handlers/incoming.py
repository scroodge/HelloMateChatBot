"""Shared incoming text message pipeline."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from telegram.ext import ContextTypes

from app.services.contact_facts_service import ContactFactsService
from app.services.conversation_starter_service import ConversationStarterService
from app.services.event_service import (
    AI_REPLY_SENT,
    GREETING_SENT,
    MESSAGE_RECEIVED,
    EventService,
)
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.memory_service import MemoryService
from app.services.profile_service import ProfileService
from app.services.reply_debounce_service import ReplyDebounceService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService
from app.services.style_service import StyleService
from app.services.summary_service import SummaryService

logger = logging.getLogger(__name__)

ReplyFn = Callable[[str], Awaitable[None]]


async def handle_incoming_text(
    *,
    contact_user_id: int,
    message_text: str,
    context: ContextTypes.DEFAULT_TYPE,
    reply_fn: ReplyFn,
    sender_is_owner: bool = False,
    contact_display_name: str | None = None,
    reply_mode: str = "auto",
    reply_context: str | None = None,
) -> None:
    """Process an incoming text message for a contact.

    Contact messages are debounced so rapid short messages are answered once.
    Owner messages are recorded immediately and flush any pending contact buffer.

    reply_mode controls how AI replies are delivered for contact messages:
    - "auto"    — reply directly via reply_fn (default, used for direct bot chat)
    - "suggest" — store a draft in the Suggest Inbox (Mini App); nothing is sent
                  to the chat
    - "off"     — skip AI reply entirely
    """

    debounce_service = context.bot_data.get("reply_debounce_service")
    if isinstance(debounce_service, ReplyDebounceService) and debounce_service.enabled:
        if sender_is_owner:
            await debounce_service.flush_now(contact_user_id)
            await _process_incoming_text(
                contact_user_id=contact_user_id,
                message_text=message_text,
                context=context,
                reply_fn=reply_fn,
                sender_is_owner=True,
                contact_display_name=contact_display_name,
                reply_mode=reply_mode,
                reply_context=reply_context,
            )
            return

        async def on_flush(combined_text: str, combined_reply_context: str | None) -> None:
            await _process_incoming_text(
                contact_user_id=contact_user_id,
                message_text=combined_text,
                context=context,
                reply_fn=reply_fn,
                sender_is_owner=False,
                contact_display_name=contact_display_name,
                reply_mode=reply_mode,
                reply_context=combined_reply_context,
            )

        await debounce_service.enqueue(
            contact_user_id,
            message_text,
            reply_context=reply_context,
            on_flush=on_flush,
        )
        return

    await _process_incoming_text(
        contact_user_id=contact_user_id,
        message_text=message_text,
        context=context,
        reply_fn=reply_fn,
        sender_is_owner=sender_is_owner,
        contact_display_name=contact_display_name,
        reply_mode=reply_mode,
        reply_context=reply_context,
    )


async def _process_incoming_text(
    *,
    contact_user_id: int,
    message_text: str,
    context: ContextTypes.DEFAULT_TYPE,
    reply_fn: ReplyFn,
    sender_is_owner: bool = False,
    contact_display_name: str | None = None,
    reply_mode: str = "auto",
    reply_context: str | None = None,
) -> None:
    """Run greeting / memory / AI logic for a (possibly batched) message."""

    greeting_service = context.bot_data.get("greeting_service")
    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    settings_service = context.bot_data.get("settings_service")
    starter_service = context.bot_data.get("starter_service")
    memory_service = context.bot_data.get("memory_service")
    profile_service = context.bot_data.get("profile_service")
    reply_service = context.bot_data.get("reply_service")
    event_service = context.bot_data.get("event_service")
    greeting_text = context.bot_data.get("greeting_text", "")
    timezone = context.bot_data.get("timezone")

    if not isinstance(settings_service, SettingsService):
        logger.error("Settings service is not configured")
        return

    if isinstance(profile_service, ProfileService):
        profile_service.get_or_create_profile(
            contact_user_id,
            display_name=contact_display_name,
        )

    if isinstance(memory_service, MemoryService) and message_text:
        if sender_is_owner:
            # Real human reply typed by the owner — feeds style learning.
            memory_service.record_assistant_message(
                contact_user_id, message_text, authored_by="owner"
            )
        else:
            memory_service.record_user_message(contact_user_id, message_text)

    if isinstance(event_service, EventService):
        event_service.record(contact_user_id, MESSAGE_RECEIVED)

    summary_service = context.bot_data.get("summary_service")
    if isinstance(summary_service, SummaryService) and message_text:
        summary_service.schedule_refresh(contact_user_id)

    facts_service = context.bot_data.get("facts_service")
    if isinstance(facts_service, ContactFactsService) and message_text and not sender_is_owner:
        facts_service.schedule_extraction(contact_user_id)

    recall_service = context.bot_data.get("recall_service")
    if recall_service is not None and message_text and not sender_is_owner:
        recall_service.schedule_index(contact_user_id)

    suggestions_service = context.bot_data.get("suggestions_service")

    # Owner replies feed style learning; refresh the profile after an owner message.
    style_service = context.bot_data.get("style_service")
    if isinstance(style_service, StyleService) and message_text and sender_is_owner:
        style_service.schedule_refresh(contact_user_id)

    if sender_is_owner:
        return

    if not isinstance(greeting_service, GreetingService):
        logger.error("Greeting service is not configured")
        return
    if not isinstance(greeting_text, str):
        logger.error("Greeting text is not configured")
        return

    # A greeting is an automatic message to the contact. Outside "auto" mode the
    # bot must never write to the contact on its own, so suppress greetings in
    # suggest/off and route straight to the (mode-aware) reply delivery.
    if reply_mode != "auto" or not settings_service.is_greeting_enabled(contact_user_id):
        await _deliver_ai_reply(
            contact_user_id=contact_user_id,
            message_text=message_text,
            reply_service=reply_service,
            reply_fn=reply_fn,
            reply_mode=reply_mode,
            event_service=event_service,
            suggestions_service=suggestions_service,
            reply_context=reply_context,
        )
        return

    sent_greeting = False
    now = datetime.now(tz=timezone) if timezone is not None else datetime.now()

    has_rules = isinstance(
        greeting_rules_service, GreetingRulesService
    ) and greeting_rules_service.has_rules(contact_user_id)
    if has_rules:
        due_rules = greeting_rules_service.get_due_rules(contact_user_id, now, require_hour=False)
        if due_rules:
            rule = due_rules[0]
            await reply_fn(rule.text)
            if isinstance(memory_service, MemoryService):
                memory_service.record_assistant_message(contact_user_id, rule.text)
            greeting_rules_service.mark_sent(rule.id, now.date())
            sent_greeting = True
            if isinstance(event_service, EventService):
                event_service.record(contact_user_id, GREETING_SENT)
    else:
        user_settings = settings_service.get_user_settings(contact_user_id)
        starters = (
            starter_service if isinstance(starter_service, ConversationStarterService) else None
        )
        if greeting_service.should_send_greeting(contact_user_id, user_settings, now=now):
            text = settings_service.resolve_greeting_text(
                contact_user_id,
                greeting_text,
                starters,
            )

            await reply_fn(text)
            if isinstance(memory_service, MemoryService):
                memory_service.record_assistant_message(contact_user_id, text)
            sent_greeting = True
            if isinstance(event_service, EventService):
                event_service.record(contact_user_id, GREETING_SENT)

    if sent_greeting:
        return

    await _deliver_ai_reply(
        contact_user_id=contact_user_id,
        message_text=message_text,
        reply_service=reply_service,
        reply_fn=reply_fn,
        reply_mode=reply_mode,
        event_service=event_service,
        suggestions_service=suggestions_service,
        reply_context=reply_context,
    )


async def _deliver_ai_reply(
    *,
    contact_user_id: int,
    message_text: str,
    reply_service: ReplyService | None,
    reply_fn: ReplyFn,
    reply_mode: str,
    event_service: EventService | None,
    suggestions_service: object | None = None,
    reply_context: str | None = None,
) -> None:
    """Route AI reply based on mode: auto sends directly, suggest stores to inbox, off skips."""

    logger.info(
        "deliver_ai_reply contact=%s mode=%s has_reply_service=%s",
        contact_user_id,
        reply_mode,
        isinstance(reply_service, ReplyService),
    )

    if reply_mode == "off":
        return

    if not isinstance(reply_service, ReplyService):
        return

    if reply_mode == "suggest":
        # Suggest mode never writes to the chat: the draft is stored in the
        # Suggest Inbox (Mini App) only. No DM, no message to the contact.
        draft = await reply_service.draft_reply(
            contact_user_id, message_text, reply_context=reply_context
        )
        logger.info(
            "suggest draft for contact=%s: %s",
            contact_user_id,
            "stored" if draft else "None",
        )
        if draft and suggestions_service is not None:
            suggestions_service.record(contact_user_id, message_text, draft)
        return

    # auto (default)
    reply = await reply_service.generate_reply(
        contact_user_id, message_text, reply_context=reply_context
    )
    if reply:
        await reply_fn(reply)
        if isinstance(event_service, EventService):
            event_service.record(contact_user_id, AI_REPLY_SENT)
