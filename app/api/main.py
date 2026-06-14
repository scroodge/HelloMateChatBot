"""FastAPI application for HelloMate Mini App."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import create_router
from app.config import Config
from app.database.sqlite import SQLiteDatabase
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.profile_service import ProfileService
from app.services.settings_service import SettingsService

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_api_app(config: Config, database: SQLiteDatabase) -> FastAPI:
    """Create the FastAPI app bound to the shared SQLite database."""

    profile_service = ProfileService(database.profiles, config.timezone_name)
    mood_service = MoodService(database.moods)
    memory_service = MemoryService(database.memory, config.memory_window_size)
    settings_service = SettingsService(
        database.settings,
        config.default_language,
        config.greeting_hour,
    )

    app = FastAPI(title="HelloMate API")
    app.include_router(
        create_router(
            config.bot_token,
            profile_service,
            mood_service,
            memory_service,
            settings_service,
        ),
        prefix="/api",
    )

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/")
        async def dashboard() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    return app
