"""Admin-only API routes for the HelloMate owner console (Phase 7A/7B/7C).

All routes under /admin require the caller to be a registered admin_user_id.
Auth is via Telegram Mini App initData in the X-Telegram-Init-Data header.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.api.auth import validate_init_data
from app.database.repositories.events import EventRepository
from app.services.contact_facts_service import ContactFactsService
from app.services.greeting_rules_service import GreetingRulesService
from app.services.greeting_service import GreetingService
from app.services.memory_service import MemoryService
from app.services.mood_service import MoodService
from app.services.persona_service import PersonaService
from app.services.profile_service import ProfileService
from app.services.reply_service import ReplyService
from app.services.settings_service import SettingsService

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PersonaWriteRequest(BaseModel):
    raw_prompt: str | None = None
    preset: str | None = None
    relationship: str | None = None
    tone: str | None = None
    topics: list[str] | None = None
    boundaries: list[str] | None = None
    clear_raw: bool = False
    clear_structured: bool = False


class PersonaTestRequest(BaseModel):
    user_id: int
    message: str
    system_prompt_override: str | None = None


class UserSettingsWriteRequest(BaseModel):
    language: str | None = None
    greeting_enabled: bool | None = None
    greeting_hour: int | None = None
    use_starters: bool | None = None
    greeting_text: str | None = None
    business_reply_mode: str | None = None  # "auto" | "suggest" | "off" | null=inherit global
    openness: str | None = None  # "open" | "neutral" | "reserved" | null=inherit global
    style_learning_enabled: bool | None = None


class ContactFactWriteRequest(BaseModel):
    value: str


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_admin_router(
    bot_token: str,
    admin_user_ids: set[int],
    profile_service: ProfileService,
    mood_service: MoodService,
    memory_service: MemoryService,
    settings_service: SettingsService,
    persona_service: PersonaService,
    reply_service: ReplyService,
    greeting_service: GreetingService,
    greeting_rules_service: GreetingRulesService,
    event_repository: EventRepository | None = None,
    facts_service: ContactFactsService | None = None,
    *,
    mini_app_dev: bool = False,
    dev_user_id: int | None = None,
) -> APIRouter:
    """Build admin API routes with injected services."""

    router = APIRouter(prefix="/admin", tags=["admin"])

    # -----------------------------------------------------------------------
    # Auth dependency
    # -----------------------------------------------------------------------

    def _get_admin_user_id(x_telegram_init_data: str | None = Header(default=None)) -> int:
        parsed = validate_init_data(x_telegram_init_data or "", bot_token)
        if parsed is not None and "user_id" in parsed:
            caller_id = int(parsed["user_id"])
        elif mini_app_dev and dev_user_id is not None:
            caller_id = dev_user_id
        else:
            raise HTTPException(status_code=401, detail="Invalid Telegram init data")
        if admin_user_ids and caller_id not in admin_user_ids:
            raise HTTPException(status_code=403, detail="Admin access required")
        return caller_id

    AdminUser = Depends(_get_admin_user_id)

    # -----------------------------------------------------------------------
    # 7A: Contacts roster
    # -----------------------------------------------------------------------

    @router.get("/users")
    async def list_users(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Return all contacts the bot has interacted with.

        Sourced from user_profiles (a row is created on the first message) so
        contacts appear in the roster even before any setting is edited. Any
        settings-only users (edited but never profiled) are unioned in too.
        """
        profiles = {p.user_id: p for p in profile_service.list_profiles()}
        settings_by_id = {s.user_id: s for s in settings_service.list_all_user_settings()}
        user_ids = (set(profiles) | set(settings_by_id)) - admin_user_ids

        result = []
        for user_id in user_ids:
            profile = profiles.get(user_id)
            settings = settings_by_id.get(user_id) or settings_service.get_user_settings(user_id)
            _, persona_source = persona_service.resolve(user_id, language=settings.language)
            result.append(
                {
                    "user_id": user_id,
                    "display_name": profile.display_name if profile else None,
                    "language": settings.language,
                    "greeting_enabled": settings.greeting_enabled,
                    "persona_source": persona_source,
                    "last_seen_at": profile.last_seen_at.isoformat() if profile else None,
                }
            )
        result.sort(
            key=lambda r: (r["last_seen_at"] is None, r["last_seen_at"] or ""),
            reverse=True,
        )
        return result

    @router.get("/users/{user_id}")
    async def get_user(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Return full info for a single contact."""
        settings = settings_service.get_user_settings(user_id)
        profile = profile_service.get_profile(user_id)
        prompt, persona_source = persona_service.resolve(
            user_id, language=settings.language
        )
        recent_mood = mood_service.latest_mood(user_id)
        recent_messages = memory_service.repository.list_messages(user_id, limit=5)

        topics_parsed = None
        if settings.persona_topics:
            try:
                topics_parsed = json.loads(settings.persona_topics)
            except (json.JSONDecodeError, TypeError):
                topics_parsed = None

        boundaries_parsed = None
        if settings.persona_boundaries:
            try:
                boundaries_parsed = json.loads(settings.persona_boundaries)
            except (json.JSONDecodeError, TypeError):
                boundaries_parsed = None

        contact_facts = (
            {f.key: f.value for f in facts_service.get_facts(user_id)}
            if facts_service is not None
            else {}
        )

        style = memory_service.get_style_profile(user_id)

        return {
            "user_id": user_id,
            "display_name": profile.display_name if profile else None,
            "timezone": profile_service.effective_timezone(user_id) if profile else None,
            "language": settings.language,
            "greeting_enabled": settings.greeting_enabled,
            "greeting_hour": settings.greeting_hour,
            "use_starters": settings.use_starters,
            "greeting_text": settings.greeting_text,
            "business_reply_mode": settings.business_reply_mode,
            "effective_business_reply_mode": settings_service.get_business_reply_mode(user_id),
            "openness": settings.openness,
            "effective_openness": settings_service.get_openness(user_id),
            "style_learning_enabled": settings.style_learning_enabled,
            "style_profile": style.profile if style else None,
            "persona": {
                "source": persona_source,
                "resolved_prompt": prompt,
                "raw_prompt": settings.persona_prompt,
                "preset": settings.persona_preset,
                "relationship": settings.persona_relationship,
                "tone": settings.persona_tone,
                "topics": topics_parsed,
                "boundaries": boundaries_parsed,
            },
            "latest_mood": recent_mood.mood if recent_mood else None,
            "recent_messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                for m in recent_messages
            ],
            "facts": contact_facts,
        }

    # -----------------------------------------------------------------------
    # 7B: Prompt playground
    # -----------------------------------------------------------------------

    @router.get("/presets")
    async def list_presets(caller_id: int = AdminUser) -> list[dict[str, Any]]:
        """Return all available persona presets."""
        return persona_service.list_presets()

    @router.post("/persona/test")
    async def test_persona(
        request: PersonaTestRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Dry-run a persona: generate a reply without recording it to memory.

        If system_prompt_override is provided it replaces the resolved persona prompt.
        Returns the reply, the full assembled_messages list, and latency_ms.
        """
        if not reply_service.enabled:
            raise HTTPException(
                status_code=503,
                detail="AI replies are not enabled (AI_REPLIES_ENABLED=false)",
            )

        result = await reply_service.preview_reply(
            request.user_id,
            request.message,
            system_prompt_override=request.system_prompt_override,
        )
        return result

    # -----------------------------------------------------------------------
    # 7C: Write endpoints
    # -----------------------------------------------------------------------

    @router.put("/users/{user_id}/persona")
    async def set_persona(
        user_id: int, request: PersonaWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Update persona for a contact.

        - raw_prompt sets the full system prompt (overrides structured)
        - clear_raw removes the raw prompt
        - structured fields (preset/relationship/tone/topics/boundaries) build a prompt
        - clear_structured removes all structured fields
        """
        try:
            if request.clear_raw:
                persona_service.set_raw_prompt(user_id, None)

            if request.clear_structured:
                persona_service.clear_structured(user_id)

            if request.raw_prompt is not None:
                persona_service.set_raw_prompt(user_id, request.raw_prompt)

            if any(
                v is not None
                for v in [
                    request.preset,
                    request.relationship,
                    request.tone,
                    request.topics,
                    request.boundaries,
                ]
            ):
                persona_service.set_structured(
                    user_id,
                    preset=request.preset,
                    relationship=request.relationship,
                    tone=request.tone,
                    topics=request.topics,
                    boundaries=request.boundaries,
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        settings = settings_service.get_user_settings(user_id)
        prompt, source = persona_service.resolve(user_id, language=settings.language)
        return {"user_id": user_id, "resolved_prompt": prompt, "source": source}

    @router.put("/users/{user_id}/settings")
    async def update_user_settings(
        user_id: int, request: UserSettingsWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Update per-user bot settings (language, greeting, starters, reply mode)."""
        from dataclasses import replace

        current = settings_service.get_user_settings(user_id)
        # business_reply_mode and openness can be explicitly cleared to null
        # (inherit global), so they are handled separately from the simple path.
        nullable_keys = {"business_reply_mode", "openness"}
        simple_fields = {
            k: v
            for k, v in request.model_dump().items()
            if v is not None and k not in nullable_keys
        }
        updated = replace(current, **simple_fields)

        if "business_reply_mode" in request.model_fields_set:
            mode = request.business_reply_mode
            if mode is not None and mode not in {"auto", "suggest", "off"}:
                raise HTTPException(
                    status_code=422,
                    detail="business_reply_mode must be 'auto', 'suggest', 'off', or null",
                )
            updated = replace(updated, business_reply_mode=mode)

        if "openness" in request.model_fields_set:
            openness = request.openness
            if openness is not None and openness not in {"open", "neutral", "reserved"}:
                raise HTTPException(
                    status_code=422,
                    detail="openness must be 'open', 'neutral', 'reserved', or null",
                )
            updated = replace(updated, openness=openness)

        try:
            saved = settings_service.save_user_settings(updated)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "user_id": saved.user_id,
            "language": saved.language,
            "greeting_enabled": saved.greeting_enabled,
            "greeting_hour": saved.greeting_hour,
            "use_starters": saved.use_starters,
            "greeting_text": saved.greeting_text,
            "business_reply_mode": saved.business_reply_mode,
            "effective_business_reply_mode": settings_service.get_business_reply_mode(user_id),
            "openness": saved.openness,
            "effective_openness": settings_service.get_openness(user_id),
            "style_learning_enabled": saved.style_learning_enabled,
        }

    # -----------------------------------------------------------------------
    # 11: Contact facts
    # -----------------------------------------------------------------------

    @router.get("/users/{user_id}/facts")
    async def get_facts(user_id: int, caller_id: int = AdminUser) -> dict[str, str]:
        """Return all durable facts extracted for a contact."""
        if facts_service is None:
            return {}
        return facts_service.facts_as_dict(user_id)

    @router.put("/users/{user_id}/facts/{key}")
    async def set_fact(
        user_id: int, key: str, request: ContactFactWriteRequest, caller_id: int = AdminUser
    ) -> dict[str, str]:
        """Manually set or override a fact for a contact."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        try:
            facts_service.set_fact(user_id, key, request.value.strip())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return facts_service.facts_as_dict(user_id)

    @router.delete("/users/{user_id}/facts/{key}")
    async def delete_fact(
        user_id: int, key: str, caller_id: int = AdminUser
    ) -> dict[str, str]:
        """Delete a single fact for a contact."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        facts_service.delete_fact(user_id, key)
        return facts_service.facts_as_dict(user_id)

    @router.delete("/users/{user_id}/facts")
    async def clear_facts(user_id: int, caller_id: int = AdminUser) -> dict[str, str]:
        """Delete all facts for a contact."""
        if facts_service is None:
            raise HTTPException(status_code=503, detail="Facts service not enabled")
        facts_service.clear_facts(user_id)
        return {}

    # -----------------------------------------------------------------------
    # 12: Learned owner style
    # -----------------------------------------------------------------------

    @router.delete("/users/{user_id}/style")
    async def clear_style(user_id: int, caller_id: int = AdminUser) -> dict[str, Any]:
        """Clear the learned owner-style profile for a contact (it will re-learn)."""
        memory_service.delete_style_profile(user_id)
        return {"user_id": user_id, "style_profile": None}

    @router.get("/settings")
    async def get_global_settings(caller_id: int = AdminUser) -> dict[str, Any]:
        """Return all global bot settings."""
        return settings_service.list_bot_settings()

    @router.put("/settings/{key}")
    async def set_global_setting(
        key: str, value: str, caller_id: int = AdminUser
    ) -> dict[str, str]:
        """Set a global bot setting."""
        settings_service.set_bot_setting(key, value)
        return {"key": key, "value": value}

    # -----------------------------------------------------------------------
    # 7D: Stats
    # -----------------------------------------------------------------------

    @router.get("/stats")
    async def get_stats(
        days: int = 30, caller_id: int = AdminUser
    ) -> dict[str, Any]:
        """Return usage stats for the last N days (default 30)."""
        from datetime import datetime, timedelta

        since = datetime.now() - timedelta(days=days)

        if event_repository is None:
            return {"error": "event_repository not configured", "days": days}

        type_counts = event_repository.type_counts(since=since)
        messages_per_user = event_repository.counts_per_user("message_received", since=since)
        replies_per_user = event_repository.counts_per_user("ai_reply_sent", since=since)

        # Source contacts from profiles (created on first message) so everyone
        # the bot has seen shows up, plus any users that have event activity.
        profiles = {p.user_id: p for p in profile_service.list_profiles()}
        contact_ids = (
            set(profiles) | set(messages_per_user) | set(replies_per_user)
        ) - admin_user_ids

        per_user = []
        for user_id in contact_ids:
            profile = profiles.get(user_id)
            per_user.append(
                {
                    "user_id": user_id,
                    "display_name": profile.display_name if profile else None,
                    "messages": messages_per_user.get(user_id, 0),
                    "ai_replies": replies_per_user.get(user_id, 0),
                    "last_seen_at": (
                        profile.last_seen_at.isoformat() if profile else None
                    ),
                }
            )

        per_user.sort(key=lambda x: x["messages"], reverse=True)

        return {
            "period_days": days,
            "since": since.isoformat(),
            "totals": type_counts,
            "contacts": per_user,
        }

    return router
