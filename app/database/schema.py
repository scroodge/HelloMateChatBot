"""Backend-agnostic SQLAlchemy Core schema for HelloMate.

This is the single source of truth for the database structure across SQLite
(local/tests) and PostgreSQL (production). Timestamps are stored as ISO-8601
text to keep identical semantics on both backends and avoid timezone-coercion
differences; the application parses them with ``datetime.fromisoformat``.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Table,
    Text,
)

metadata = MetaData()

user_greetings = Table(
    "user_greetings",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("last_greeting_date", Text, nullable=False),
    Column("updated_at", Text),
)

user_settings = Table(
    "user_settings",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("language", Text, nullable=False, default="ru"),
    Column("greeting_enabled", Boolean, nullable=False, default=True),
    Column("greeting_hour", Integer, nullable=False, default=9),
    Column("use_starters", Boolean, nullable=False, default=False),
    Column("greeting_text", Text),
    Column("greeting_interval", Text, nullable=False, default="daily"),
    Column("greeting_weekday", Integer, nullable=False, default=0),
    Column("greeting_day", Integer, nullable=False, default=1),
    Column("persona_prompt", Text),
    # structured persona fields (slice 6A)
    Column("persona_preset", Text),          # e.g. "friend", "family", "mentor"
    Column("persona_relationship", Text),    # free-text e.g. "older brother"
    Column("persona_tone", Text),            # e.g. "warm", "formal", "playful"
    Column("persona_topics", Text),          # JSON list of allowed topics
    Column("persona_boundaries", Text),      # JSON list of forbidden topics
    Column("business_reply_mode", Text),     # "auto" | "suggest" | "off" | NULL=inherit global
    Column("openness", Text),                # "open" | "neutral" | "reserved" | NULL=inherit global
    Column("style_learning_enabled", Boolean, nullable=False, default=False),
    Column("updated_at", Text),
)

bot_settings = Table(
    "bot_settings",
    metadata,
    Column("key", Text, primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", Text),
)

user_profiles = Table(
    "user_profiles",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("display_name", Text),
    Column("timezone_override", Text),
    Column("created_at", Text, nullable=False),
    Column("last_seen_at", Text, nullable=False),
)

mood_entries = Table(
    "mood_entries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("mood", Integer, nullable=False),
    Column("note", Text),
    Column("recorded_at", Text, nullable=False),
    Index("idx_mood_entries_user_recorded", "user_id", "recorded_at"),
)

conversation_messages = Table(
    "conversation_messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("role", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    # "contact" | "owner" (real human reply) | "bot" (AI-generated) | NULL (legacy)
    Column("authored_by", Text),
    Index("idx_conversation_messages_user_created", "user_id", "created_at"),
)

conversation_summaries = Table(
    "conversation_summaries",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("summary", Text, nullable=False),
    # how many of the oldest messages are already folded into this summary
    Column("covered_count", Integer, nullable=False, default=0),
    Column("updated_at", Text, nullable=False),
)

contact_style_profiles = Table(
    "contact_style_profiles",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("profile", Text, nullable=False),
    # how many owner-authored messages are already folded into this profile
    Column("covered_count", Integer, nullable=False, default=0),
    Column("updated_at", Text, nullable=False),
)

documents = Table(
    "documents",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("title", Text),
    Column("content", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Index("idx_documents_user", "user_id"),
)

document_chunks = Table(
    "document_chunks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("document_id", Integer, nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column("content", Text, nullable=False),
    Column("embedding", LargeBinary),
    Index("idx_document_chunks_document", "document_id"),
)

events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("meta", Text),  # JSON payload (optional)
    Column("created_at", Text, nullable=False),
    Index("idx_events_user_created", "user_id", "created_at"),
    Index("idx_events_type_created", "event_type", "created_at"),
)

business_connections = Table(
    "business_connections",
    metadata,
    Column("connection_id", Text, primary_key=True),
    Column("owner_user_id", Integer, nullable=False),
    Column("is_enabled", Boolean, nullable=False, default=True),
    Column("updated_at", Text, nullable=False),
    Index("idx_business_connections_owner", "owner_user_id"),
)

business_chats = Table(
    "business_chats",
    metadata,
    Column("chat_id", Integer, primary_key=True, autoincrement=False),
    Column("contact_user_id", Integer, nullable=False),
    Column("connection_id", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("idx_business_chats_contact", "contact_user_id"),
    Index("idx_business_chats_connection", "connection_id"),
)

contact_facts = Table(
    "contact_facts",
    metadata,
    Column("user_id", Integer, nullable=False),
    Column("key", Text, nullable=False),
    Column("value", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Index("pk_contact_facts", "user_id", "key", unique=True),
)

contact_facts_meta = Table(
    "contact_facts_meta",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("last_message_count", Integer, nullable=False, default=0),
    Column("updated_at", Text, nullable=False),
)

conversation_message_embeddings = Table(
    "conversation_message_embeddings",
    metadata,
    Column("message_id", Integer, primary_key=True, autoincrement=False),
    Column("user_id", Integer, nullable=False),
    Column("embedding", LargeBinary, nullable=False),
    Index("idx_message_embeddings_user", "user_id"),
)

recall_index_meta = Table(
    "recall_index_meta",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("watermark_id", Integer, nullable=False, default=0),
    Column("updated_at", Text, nullable=False),
)

user_greeting_rules = Table(
    "user_greeting_rules",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("text", Text, nullable=False),
    Column("greeting_interval", Text, nullable=False, default="daily"),
    Column("greeting_hour", Integer, nullable=False, default=9),
    Column("greeting_weekday", Integer, nullable=False, default=0),
    Column("greeting_day", Integer, nullable=False, default=1),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("last_sent_date", Text),
    Column("created_at", Text),
    Column("updated_at", Text),
    Index("idx_greeting_rules_user_id", "user_id"),
)
