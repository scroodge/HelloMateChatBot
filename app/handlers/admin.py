"""Admin command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.auth.admin import require_admin
from app.handlers.helpers import get_language
from app.i18n import supported_languages, translate
from app.models.settings import UserSettings
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_schedule import (
    format_rule,
    format_schedule,
    parse_greeting_schedule_args,
)
from app.services.greeting_service import GreetingService
from app.services.settings_service import PERSONA_PROMPT_MAX_LENGTH, SettingsService


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin."""

    if not await require_admin(update, context):
        return
    language = get_language(update, context)
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(translate("admin_help", language))


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) >= 3 and context.args[0] == "set":
        key = context.args[1]
        value = " ".join(context.args[2:])
        settings_service.set_bot_setting(key, value)
        await update.effective_message.reply_text(translate("settings_updated", language, key=key))
        return

    if context.args:
        await update.effective_message.reply_text(translate("settings_usage", language))
        return

    settings = settings_service.list_bot_settings()
    if not settings:
        await update.effective_message.reply_text(translate("settings_title", language))
        return

    lines = [translate("settings_title", language)]
    lines.extend(
        translate("settings_item", language, key=key, value=value)
        for key, value in sorted(settings.items())
    )
    await update.effective_message.reply_text("\n".join(lines))


async def setlang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setlang."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(translate("setlang_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    requested = context.args[1].strip().lower()
    if requested not in supported_languages():
        await update.effective_message.reply_text(
            translate("lang_invalid", language, languages=", ".join(supported_languages()))
        )
        return

    settings_service.set_language(user_id, requested)
    await update.effective_message.reply_text(
        translate("setlang_updated", language, user_id=user_id, lang=requested)
    )


async def setgreeting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setgreeting."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(translate("setgreeting_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    state = context.args[1].strip().lower()
    enabled = state in {"on", "1", "true", "yes"}
    if state not in {"on", "off", "1", "0", "true", "false", "yes", "no"}:
        await update.effective_message.reply_text(translate("setgreeting_usage", language))
        return

    settings_service.set_greeting_enabled(user_id, enabled)
    await update.effective_message.reply_text(
        translate(
            "setgreeting_updated",
            language,
            user_id=user_id,
            state=translate("on" if enabled else "off", language),
        )
    )


async def setgreettext_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setgreettext."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) < 2:
        await update.effective_message.reply_text(translate("setgreettext_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    text = " ".join(context.args[1:]).strip()
    if text in {"-", "clear", "default"}:
        settings_service.set_greeting_text(user_id, None)
        await update.effective_message.reply_text(
            translate("setgreettext_cleared", language, user_id=user_id)
        )
        return

    settings_service.set_greeting_text(user_id, text)
    await update.effective_message.reply_text(
        translate("setgreettext_updated", language, user_id=user_id, text=text)
    )


async def setpersona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setpersona."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) < 2:
        await update.effective_message.reply_text(translate("setpersona_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    text = " ".join(context.args[1:]).strip()
    if text in {"-", "clear", "default"}:
        settings_service.set_persona_prompt(user_id, None)
        await update.effective_message.reply_text(
            translate("setpersona_cleared", language, user_id=user_id)
        )
        return

    try:
        settings_service.set_persona_prompt(user_id, text)
    except ValueError as error:
        if "empty" in str(error):
            await update.effective_message.reply_text(translate("setpersona_empty", language))
            return
        if "at most" in str(error):
            await update.effective_message.reply_text(
                translate("setpersona_too_long", language, max_length=PERSONA_PROMPT_MAX_LENGTH)
            )
            return
        raise

    await update.effective_message.reply_text(
        translate("setpersona_updated", language, user_id=user_id, length=len(text))
    )


async def getpersona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /getpersona."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) != 1:
        await update.effective_message.reply_text(translate("getpersona_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    source = settings_service.persona_source(user_id)
    user_language = settings_service.get_language(user_id)
    prompt = settings_service.resolve_persona_prompt(user_id, user_language)
    source_label = translate(f"persona_source_{source}", language)
    display_prompt = prompt
    truncated = False
    if len(display_prompt) > 3500:
        display_prompt = f"{display_prompt[:3500]}..."
        truncated = True

    lines = [
        translate("getpersona_title", language, user_id=user_id, source=source_label),
        display_prompt,
    ]
    if truncated:
        lines.append(translate("getpersona_truncated", language))
    await update.effective_message.reply_text("\n\n".join(lines))


async def setstarters_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setstarters."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(translate("setstarters_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    state = context.args[1].strip().lower()
    enabled = state in {"on", "1", "true", "yes"}
    if state not in {"on", "off", "1", "0", "true", "false", "yes", "no"}:
        await update.effective_message.reply_text(translate("setstarters_usage", language))
        return

    settings_service.set_use_starters(user_id, enabled)
    await update.effective_message.reply_text(
        translate(
            "setstarters_updated",
            language,
            user_id=user_id,
            state=translate("on" if enabled else "off", language),
        )
    )


async def setgreetschedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setgreetschedule."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) < 2:
        await update.effective_message.reply_text(translate("setgreetschedule_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    if isinstance(greeting_rules_service, GreetingRulesService) and greeting_rules_service.has_rules(
        user_id
    ):
        await update.effective_message.reply_text(translate("use_addgreeting_instead", language))
        return

    parsed = parse_greeting_schedule_args(context.args[1:])
    if parsed is None:
        await update.effective_message.reply_text(translate("setgreetschedule_usage", language))
        return

    settings_service.set_greeting_schedule(
        user_id,
        parsed.interval,
        hour=parsed.hour,
        weekday=parsed.weekday,
        day_of_month=parsed.day_of_month,
    )
    updated = settings_service.get_user_settings(user_id)
    await update.effective_message.reply_text(
        translate(
            "setgreetschedule_updated",
            language,
            user_id=user_id,
            schedule=format_schedule(updated, language),
        )
    )


async def listgreetings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /greetings."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    if not isinstance(greeting_rules_service, GreetingRulesService):
        return

    language = get_language(update, context)
    if len(context.args) != 1:
        await update.effective_message.reply_text(translate("greetings_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    rules = greeting_rules_service.list_rules(user_id)
    if not rules:
        await update.effective_message.reply_text(translate("greetings_empty", language, user_id=user_id))
        return

    lines = [translate("greetings_title", language, user_id=user_id)]
    lines.extend(format_rule(rule, index, language) for index, rule in enumerate(rules, start=1))
    await update.effective_message.reply_text("\n".join(lines))


async def addgreeting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /addgreeting."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    settings_service = context.bot_data.get("settings_service")
    if not isinstance(greeting_rules_service, GreetingRulesService):
        return
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) < 3:
        await update.effective_message.reply_text(translate("addgreeting_usage", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    current = settings_service.get_user_settings(user_id)
    parsed = parse_greeting_schedule_args(
        context.args[1:],
        default_hour=current.greeting_hour,
        require_text=True,
    )
    if parsed is None:
        await update.effective_message.reply_text(translate("addgreeting_usage", language))
        return

    rule = greeting_rules_service.add_rule(
        user_id,
        parsed.text,
        parsed.interval,
        hour=parsed.hour,
        weekday=parsed.weekday,
        day_of_month=parsed.day_of_month,
    )
    index = len(greeting_rules_service.list_rules(user_id))
    await update.effective_message.reply_text(
        translate(
            "addgreeting_added",
            language,
            user_id=user_id,
            index=index,
            schedule=format_schedule(
                UserSettings(
                    user_id=user_id,
                    greeting_interval=rule.greeting_interval,
                    greeting_hour=rule.greeting_hour,
                    greeting_weekday=rule.greeting_weekday,
                    greeting_day=rule.greeting_day,
                ),
                language,
            ),
        )
    )


async def delgreeting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /delgreeting."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    if not isinstance(greeting_rules_service, GreetingRulesService):
        return

    language = get_language(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(translate("delgreeting_usage", language))
        return

    try:
        user_id = int(context.args[0])
        index = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    deleted = greeting_rules_service.delete_rule_by_index(user_id, index)
    if deleted is None:
        await update.effective_message.reply_text(translate("greeting_not_found", language))
        return

    await update.effective_message.reply_text(
        translate("delgreeting_deleted", language, user_id=user_id, index=index)
    )


async def togglegreeting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /togglegreeting."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    if not isinstance(greeting_rules_service, GreetingRulesService):
        return

    language = get_language(update, context)
    if len(context.args) != 3:
        await update.effective_message.reply_text(translate("togglegreeting_usage", language))
        return

    try:
        user_id = int(context.args[0])
        index = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    state = context.args[2].strip().lower()
    enabled = state in {"on", "1", "true", "yes"}
    if state not in {"on", "off", "1", "0", "true", "false", "yes", "no"}:
        await update.effective_message.reply_text(translate("togglegreeting_usage", language))
        return

    updated = greeting_rules_service.toggle_rule_by_index(user_id, index, enabled)
    if updated is None:
        await update.effective_message.reply_text(translate("greeting_not_found", language))
        return

    await update.effective_message.reply_text(
        translate(
            "togglegreeting_updated",
            language,
            user_id=user_id,
            index=index,
            state=translate("on" if enabled else "off", language),
        )
    )


async def sethour_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /sethour."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if len(context.args) != 2:
        await update.effective_message.reply_text(translate("sethour_usage", language))
        return

    try:
        user_id = int(context.args[0])
        hour = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    if not 0 <= hour <= 23:
        await update.effective_message.reply_text(translate("invalid_hour", language))
        return

    settings_service.set_greeting_hour(user_id, hour)
    await update.effective_message.reply_text(
        translate("sethour_updated", language, user_id=user_id, hour=hour)
    )


async def userinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /userinfo."""

    if not await require_admin(update, context):
        return
    if update.effective_message is None:
        return

    settings_service = context.bot_data.get("settings_service")
    greeting_service = context.bot_data.get("greeting_service")
    greeting_rules_service = context.bot_data.get("greeting_rules_service")
    if not isinstance(settings_service, SettingsService):
        return
    if not isinstance(greeting_service, GreetingService):
        return

    language = get_language(update, context)
    if len(context.args) != 1:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text(translate("invalid_user_id", language))
        return

    settings = settings_service.get_user_settings(user_id)
    last_greeting = greeting_service.get_last_greeting_date(user_id)
    lines = [
        translate("userinfo_title", language, user_id=user_id),
        translate("userinfo_language", language, language=settings.language),
        translate(
            f"userinfo_persona_{settings_service.persona_source(user_id)}",
            language,
            length=len(settings.persona_prompt or ""),
        ),
        translate(
            "userinfo_greeting",
            language,
            enabled=translate("on" if settings.greeting_enabled else "off", language),
        ),
    ]

    if isinstance(greeting_rules_service, GreetingRulesService) and greeting_rules_service.has_rules(
        user_id
    ):
        rules = greeting_rules_service.list_rules(user_id)
        lines.append(translate("userinfo_rules_count", language, count=len(rules)))
        lines.extend(format_rule(rule, index, language) for index, rule in enumerate(rules, start=1))
    else:
        lines.extend(
            [
                translate("userinfo_hour", language, hour=settings.greeting_hour),
                translate(
                    "userinfo_schedule",
                    language,
                    schedule=format_schedule(settings, language),
                ),
                translate(
                    "userinfo_greeting_text",
                    language,
                    text=settings.greeting_text or translate("userinfo_default", language),
                ),
                translate(
                    "userinfo_starters",
                    language,
                    enabled=translate("on" if settings.use_starters else "off", language),
                ),
            ]
        )

    lines.append(
        translate(
            "userinfo_last_greeting",
            language,
            date=last_greeting.isoformat() if last_greeting else "-",
        )
    )
    await update.effective_message.reply_text("\n".join(lines))
