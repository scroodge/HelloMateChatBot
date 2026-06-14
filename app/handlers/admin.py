"""Admin command handlers."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.auth.admin import require_admin
from app.handlers.helpers import get_language
from app.i18n import supported_languages, translate
from app.services.greeting_service import GreetingService
from app.services.settings_service import SettingsService


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
            "userinfo_greeting",
            language,
            enabled=translate("on" if settings.greeting_enabled else "off", language),
        ),
        translate("userinfo_hour", language, hour=settings.greeting_hour),
        translate(
            "userinfo_starters",
            language,
            enabled=translate("on" if settings.use_starters else "off", language),
        ),
        translate(
            "userinfo_last_greeting",
            language,
            date=last_greeting.isoformat() if last_greeting else "-",
        ),
    ]
    await update.effective_message.reply_text("\n".join(lines))
