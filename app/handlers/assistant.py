"""Owner personal-assistant command: /assistant.

Owner-only. Lets the owner run named assistant personas (e.g. an English
teacher) in the direct bot chat, with isolated persistent memory per profile.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.auth.admin import require_admin
from app.handlers.helpers import is_business_update
from app.services.assistant_service import AssistantService

logger = logging.getLogger(__name__)

_HELP = (
    "🤖 Личный ассистент (только для тебя)\n\n"
    "/assistant new <имя> | <персона> — создать/изменить профиль и включить\n"
    "/assistant use <имя> — переключиться на профиль (включить)\n"
    "/assistant off — выключить ассистента\n"
    "/assistant list — список профилей\n"
    "/assistant reset — очистить историю активного профиля\n"
    "/assistant del <имя> — удалить профиль\n\n"
    "Пример:\n"
    "/assistant new english | Ты учитель английского. Общайся по-английски, "
    "мягко исправляй мои ошибки и давай примеры."
)


def _status_line(svc: AssistantService, owner_id: int) -> str:
    active = svc.active_profile(owner_id)
    profiles = svc.list_profiles(owner_id)
    names = ", ".join(p.name for p in profiles) or "нет"
    if active is not None:
        state = f"включён — профиль «{active.name}»"
    else:
        state = "выключен"
    return f"Статус: {state}\nПрофили: {names}"


async def assistant_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /assistant <subcommand>."""
    if update.effective_message is None or update.effective_user is None:
        return
    if is_business_update(update):
        return
    if not await require_admin(update, context):
        return

    svc = context.bot_data.get("assistant_service")
    if not isinstance(svc, AssistantService):
        await update.effective_message.reply_text("Ассистент не сконфигурирован.")
        return

    owner_id = update.effective_user.id
    raw = update.effective_message.text or ""
    parts = raw.split(maxsplit=1)
    body = parts[1].strip() if len(parts) > 1 else ""

    if not body:
        await update.effective_message.reply_text(_status_line(svc, owner_id) + "\n\n" + _HELP)
        return

    sub_parts = body.split(maxsplit=1)
    sub = sub_parts[0].lower()
    arg = sub_parts[1].strip() if len(sub_parts) > 1 else ""

    if sub == "list":
        await update.effective_message.reply_text(_status_line(svc, owner_id))
        return

    if sub == "off":
        svc.set_active(owner_id, None)
        await update.effective_message.reply_text("🤖 Ассистент выключен.")
        return

    if sub == "reset":
        ok = svc.reset_history(owner_id)
        await update.effective_message.reply_text(
            "🧹 История активного профиля очищена." if ok else "Нет активного профиля."
        )
        return

    if sub == "use":
        if not arg:
            await update.effective_message.reply_text("Укажи имя: /assistant use <имя>")
            return
        profile = svc.activate_by_name(owner_id, arg)
        if profile is None:
            await update.effective_message.reply_text(f"Профиль «{arg}» не найден.")
            return
        await update.effective_message.reply_text(
            f"🤖 Включён профиль «{profile.name}». Пиши — отвечаю как ассистент."
        )
        return

    if sub == "del":
        if not arg:
            await update.effective_message.reply_text("Укажи имя: /assistant del <имя>")
            return
        ok = svc.delete(owner_id, arg)
        await update.effective_message.reply_text(
            f"🗑 Профиль «{arg}» удалён." if ok else f"Профиль «{arg}» не найден."
        )
        return

    if sub == "new":
        if "|" not in arg:
            await update.effective_message.reply_text(
                "Формат: /assistant new <имя> | <персона>"
            )
            return
        name, persona = (s.strip() for s in arg.split("|", 1))
        try:
            profile = svc.create_or_update(owner_id, name, persona)
        except ValueError as exc:
            await update.effective_message.reply_text(f"Ошибка: {exc}")
            return
        if profile.id is not None:
            svc.set_active(owner_id, profile.id)
        await update.effective_message.reply_text(
            f"✅ Профиль «{profile.name}» сохранён и включён. Пиши — отвечаю как ассистент."
        )
        return

    # Unknown subcommand → show help.
    await update.effective_message.reply_text(_status_line(svc, owner_id) + "\n\n" + _HELP)
