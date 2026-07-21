"""Backend-agnostic database manager (SQLite locally, PostgreSQL in production).

The bot runs Telegram handlers on the asyncio loop while the FastAPI Mini App
runs in a separate thread; SQLAlchemy's connection pool is thread-safe, so both
share one ``Database`` instance. The backend is chosen entirely by the
``DATABASE_URL`` (e.g. ``sqlite:///./data/hellomate.db`` or
``postgresql+psycopg://user:pass@host:5432/hellomate``).
"""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.database.repositories.assistant import AssistantProfilesRepositoryImpl
from app.database.repositories.business import BusinessRepositoryImpl
from app.database.repositories.documents import DocumentRepositoryImpl
from app.database.repositories.events import EventRepositoryImpl
from app.database.repositories.examples import ContactExamplesRepositoryImpl
from app.database.repositories.fact_categories import FactCategoriesRepositoryImpl
from app.database.repositories.facts import ContactFactsRepositoryImpl
from app.database.repositories.feedback import FeedbackRepositoryImpl
from app.database.repositories.greeting import GreetingRepositoryImpl
from app.database.repositories.greeting_rules import GreetingRulesRepositoryImpl
from app.database.repositories.learning_proposals import LearningProposalsRepositoryImpl
from app.database.repositories.memory import MemoryRepositoryImpl
from app.database.repositories.mood import MoodRepositoryImpl
from app.database.repositories.owner_reply_pairs import OwnerReplyPairsRepositoryImpl
from app.database.repositories.profile import ProfileRepositoryImpl
from app.database.repositories.settings import SettingsRepositoryImpl
from app.database.repositories.suggestions import SuggestionsRepositoryImpl
from app.database.schema import metadata


class Database:
    """Owns the SQLAlchemy engine and exposes repository accessors."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._engine: Engine | None = None
        self.business = BusinessRepositoryImpl(self)
        self.events = EventRepositoryImpl(self)
        self.examples = ContactExamplesRepositoryImpl(self)
        self.suggestions = SuggestionsRepositoryImpl(self)
        self.feedback = FeedbackRepositoryImpl(self)
        self.owner_reply_pairs = OwnerReplyPairsRepositoryImpl(self)
        self.learning_proposals = LearningProposalsRepositoryImpl(self)
        self.facts = ContactFactsRepositoryImpl(self)
        self.fact_categories = FactCategoriesRepositoryImpl(self)
        self.assistant_profiles = AssistantProfilesRepositoryImpl(self)
        self.greetings = GreetingRepositoryImpl(self)
        self.greeting_rules = GreetingRulesRepositoryImpl(self)
        self.settings = SettingsRepositoryImpl(self)
        self.profiles = ProfileRepositoryImpl(self)
        self.moods = MoodRepositoryImpl(self)
        self.memory = MemoryRepositoryImpl(self)
        self.documents = DocumentRepositoryImpl(self)

    def open(self) -> None:
        """Create the engine, ensure the parent directory, and provision tables."""

        connect_args: dict[str, object] = {}
        if self.database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            path = self.database_url.split("///", 1)[-1]
            if path and path != ":memory:":
                Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_engine(
            self.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self._provision_schema()

    def _provision_schema(self) -> None:
        """Bring the schema to the current head revision.

        Two cases:
        - Fresh DB (no alembic_version row): create_all builds the full schema from
          schema.py in one shot, then stamp at head. Migrations are not replayed
          because create_all already produced the same result.
        - Existing DB (already stamped): run ``alembic upgrade head`` to apply any
          pending incremental migrations (new columns, new tables, etc.).

        This means shipping a new migration is sufficient — no manual
        ``alembic upgrade`` step required in production or Docker.
        """
        from alembic.config import Config as AlembicConfig
        from alembic.runtime.migration import MigrationContext

        from alembic import command as alembic_command

        alembic_cfg = AlembicConfig()
        alembic_cfg.set_main_option("script_location", "alembic")
        alembic_cfg.set_main_option("sqlalchemy.url", self.database_url)

        with self._engine.connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()

        if current is None:
            # Fresh DB: create all tables at once, then stamp at head (skip replay)
            metadata.create_all(self._engine)
            alembic_command.stamp(alembic_cfg, "head")
        else:
            # Existing DB: apply any pending migrations
            alembic_command.upgrade(alembic_cfg, "head")

    def close(self) -> None:
        """Dispose the engine and its pooled connections."""

        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> Database:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def engine(self) -> Engine:
        """Return the active engine."""

        if self._engine is None:
            raise RuntimeError(
                "Database is not connected. Use `with Database(url):` or call open()."
            )
        return self._engine
