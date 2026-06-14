"""FastAPI routes for the Telegram Mini App."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from app.api.auth import validate_init_data
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService
from app.services.settings_service import SettingsService


def create_router(
    bot_token: str,
    profile_service: ProfileService,
    mood_service: MoodService,
    memory_service: MemoryService,
    settings_service: SettingsService,
) -> APIRouter:
    """Build API routes with injected services."""

    router = APIRouter()

    def _user_id_from_header(x_telegram_init_data: str | None) -> int:
        parsed = validate_init_data(x_telegram_init_data or "", bot_token)
        if parsed is None or "user_id" not in parsed:
            raise HTTPException(status_code=401, detail="Invalid Telegram init data")
        return int(parsed["user_id"])

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/profile")
    async def profile(x_telegram_init_data: str | None = Header(default=None)) -> dict[str, object]:
        user_id = _user_id_from_header(x_telegram_init_data)
        item = profile_service.get_or_create_profile(user_id)
        settings = settings_service.get_user_settings(user_id)
        return {
            "user_id": item.user_id,
            "display_name": item.display_name,
            "timezone": profile_service.effective_timezone(user_id),
            "language": settings.language,
            "created_at": item.created_at.isoformat(),
            "last_seen_at": item.last_seen_at.isoformat(),
        }

    @router.get("/mood")
    async def mood(
        x_telegram_init_data: str | None = Header(default=None),
    ) -> list[dict[str, object]]:
        user_id = _user_id_from_header(x_telegram_init_data)
        return [
            {
                "mood": entry.mood,
                "note": entry.note,
                "recorded_at": entry.recorded_at.isoformat(),
            }
            for entry in mood_service.recent_entries(user_id, limit=14)
        ]

    @router.get("/memory")
    async def memory(
        x_telegram_init_data: str | None = Header(default=None),
    ) -> list[dict[str, object]]:
        user_id = _user_id_from_header(x_telegram_init_data)
        return [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in memory_service.recent_messages(user_id)
        ]

    return router
