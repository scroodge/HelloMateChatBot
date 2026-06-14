"""Command handlers for HelloMate."""

from __future__ import annotations

from telegram import Update, WebAppInfo
from telegram.ext import ContextTypes

from app.handlers.helpers import get_language, reply
from app.i18n import supported_languages, translate
from app.services.profile_service import ProfileService
from app.services.rag_service import RAGService
from app.services.settings_service import SettingsService


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None or update.effective_user is None:
        return

    profile_service = context.bot_data.get("profile_service")
    if isinstance(profile_service, ProfileService):
        display_name = update.effective_user.full_name or None
        profile_service.get_or_create_profile(update.effective_user.id, display_name=display_name)

    await reply(update, "start_message", context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None:
        return

    await reply(update, "help_message", context)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /about."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None:
        return

    await reply(update, "about_message", context)


async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lang."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None or update.effective_user is None:
        return

    settings_service = context.bot_data.get("settings_service")
    if not isinstance(settings_service, SettingsService):
        return

    language = get_language(update, context)
    if not context.args:
        await update.effective_message.reply_text(translate("lang_usage", language))
        return

    requested = context.args[0].strip().lower()
    if requested not in supported_languages():
        await update.effective_message.reply_text(
            translate(
                "lang_invalid",
                language,
                languages=", ".join(supported_languages()),
            )
        )
        return

    settings_service.set_language(update.effective_user.id, requested)
    await update.effective_message.reply_text(
        translate("lang_updated", requested, language=requested)
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None or update.effective_user is None:
        return

    profile_service = context.bot_data.get("profile_service")
    if not isinstance(profile_service, ProfileService):
        return

    language = get_language(update, context)
    profile = profile_service.get_or_create_profile(
        update.effective_user.id,
        display_name=update.effective_user.full_name or None,
    )
    await update.effective_message.reply_text(
        "\n".join(
            [
                translate("profile_title", language),
                translate(
                    "profile_name",
                    language,
                    name=profile.display_name or update.effective_user.full_name,
                ),
                translate(
                    "profile_timezone",
                    language,
                    timezone=profile_service.effective_timezone(update.effective_user.id),
                ),
                translate(
                    "profile_created",
                    language,
                    created_at=profile.created_at.strftime("%Y-%m-%d"),
                ),
            ]
        )
    )


async def setname_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setname."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None or update.effective_user is None:
        return

    profile_service = context.bot_data.get("profile_service")
    if not isinstance(profile_service, ProfileService):
        return

    language = get_language(update, context)
    if not context.args:
        await update.effective_message.reply_text(translate("setname_usage", language))
        return

    name = " ".join(context.args).strip()
    profile_service.set_display_name(update.effective_user.id, name)
    await update.effective_message.reply_text(translate("setname_updated", language, name=name))


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /remember."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None or update.effective_user is None:
        return

    rag_service = context.bot_data.get("rag_service")
    if not isinstance(rag_service, RAGService):
        return

    language = get_language(update, context)
    if not context.args:
        await update.effective_message.reply_text(translate("remember_usage", language))
        return

    text = " ".join(context.args).strip()
    await rag_service.remember(update.effective_user.id, text)
    await update.effective_message.reply_text(translate("remember_saved", language, text=text))


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /dashboard."""

    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_message is None:
        return

    mini_app_url = context.bot_data.get("mini_app_url", "")
    mini_app_dev = context.bot_data.get("mini_app_dev", False)
    api_port = context.bot_data.get("api_port", 8080)
    language = get_language(update, context)
    if not mini_app_url and not mini_app_dev:
        await update.effective_message.reply_text(translate("dashboard_unavailable", language))
        return

    if mini_app_url:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        translate("dashboard_button", language),
                        web_app=WebAppInfo(url=mini_app_url),
                    )
                ]
            ]
        )
        await update.effective_message.reply_text(
            translate("dashboard_button", language),
            reply_markup=keyboard,
        )
        return

    local_url = f"http://127.0.0.1:{api_port}/"
    await update.effective_message.reply_text(
        translate("dashboard_dev_local", language, url=local_url),
    )
