"""User profile business logic."""

from __future__ import annotations

from datetime import datetime

from app.database.repositories.profile import ProfileRepository
from app.models.profile import UserProfile


class ProfileService:
    """Manage user profiles."""

    def __init__(self, repository: ProfileRepository, default_timezone: str) -> None:
        self.repository = repository
        self.default_timezone = default_timezone

    def get_or_create_profile(
        self,
        user_id: int,
        display_name: str | None = None,
        now: datetime | None = None,
    ) -> UserProfile:
        """Return an existing profile or create one."""

        current = self.repository.get_profile(user_id)
        current_time = now or datetime.now().astimezone()
        if current is not None:
            updated = UserProfile(
                user_id=current.user_id,
                display_name=display_name or current.display_name,
                timezone_override=current.timezone_override,
                created_at=current.created_at,
                last_seen_at=current_time,
            )
            return self.repository.upsert_profile(updated)

        profile = UserProfile(
            user_id=user_id,
            display_name=display_name,
            timezone_override=None,
            created_at=current_time,
            last_seen_at=current_time,
        )
        return self.repository.upsert_profile(profile)

    def get_profile(self, user_id: int) -> UserProfile | None:
        """Return a stored profile if present."""

        return self.repository.get_profile(user_id)

    def list_profiles(self) -> list[UserProfile]:
        """Return all stored profiles (everyone the bot has interacted with)."""

        return self.repository.list_profiles()

    def set_display_name(self, user_id: int, display_name: str) -> UserProfile:
        """Update a user's display name."""

        profile = self.get_or_create_profile(user_id)
        updated = UserProfile(
            user_id=profile.user_id,
            display_name=display_name,
            timezone_override=profile.timezone_override,
            created_at=profile.created_at,
            last_seen_at=profile.last_seen_at,
        )
        return self.repository.upsert_profile(updated)

    def effective_timezone(self, user_id: int) -> str:
        """Return the user's timezone override or the default."""

        profile = self.repository.get_profile(user_id)
        if profile is None or not profile.timezone_override:
            return self.default_timezone
        return profile.timezone_override
