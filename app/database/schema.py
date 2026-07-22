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
    Float,
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
    Column("persona_preset", Text),  # e.g. "friend", "family", "mentor"
    Column("persona_relationship", Text),  # free-text e.g. "older brother"
    Column("persona_tone", Text),  # e.g. "warm", "formal", "playful"
    Column("persona_topics", Text),  # JSON list of allowed topics
    Column("persona_boundaries", Text),  # JSON list of forbidden topics
    Column("business_reply_mode", Text),  # "suggest" | "off" | NULL=inherit global
    Column("openness", Text),  # "open" | "neutral" | "reserved" | NULL=inherit global
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

owner_style_profiles = Table(
    "owner_style_profiles",
    metadata,
    Column("scope_key", Text, primary_key=True),
    Column("profile", Text, nullable=False),
    # Highest conversation_messages.id folded into this aggregate profile.
    Column("covered_through_message_id", Integer, nullable=False, default=0),
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
    Column("source_message_id", Integer),
    Column("confidence", Float),
    Column("first_observed_at", Text),
    Column("last_observed_at", Text),
    Column("valid_from", Text),
    Column("valid_until", Text),
    Column("owner_confirmed", Boolean, nullable=False, default=False),
    Column("version_id", Text),
    Index("pk_contact_facts", "user_id", "key", unique=True),
)

contact_fact_history = Table(
    "contact_fact_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("key", Text, nullable=False),
    Column("value", Text, nullable=False),
    Column("source_message_id", Integer),
    Column("confidence", Float),
    Column("first_observed_at", Text),
    Column("last_observed_at", Text),
    Column("valid_from", Text),
    Column("valid_until", Text),
    Column("owner_confirmed", Boolean, nullable=False, default=False),
    Column("version_id", Text),
    Column("superseded_by", Text),
    Column("created_at", Text, nullable=False),
    Index("idx_contact_fact_history_user_key", "user_id", "key", "created_at"),
)

contact_facts_meta = Table(
    "contact_facts_meta",
    metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=False),
    Column("last_message_count", Integer, nullable=False, default=0),
    Column("updated_at", Text, nullable=False),
)

suggestions = Table(
    "suggestions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),  # the contact
    Column("contact_message", Text, nullable=False),
    Column("draft_text", Text, nullable=False),
    # "pending" | "saved" | "dismissed" | "superseded"
    Column("status", Text, nullable=False, default="pending"),
    Column("generation_trace_id", Text),
    Column("created_at", Text, nullable=False),
    Index("idx_suggestions_status_created", "status", "created_at"),
    Index("idx_suggestions_user", "user_id"),
)

owner_reply_pairs = Table(
    "owner_reply_pairs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("suggestion_id", Integer, nullable=False, unique=True),
    Column("user_id", Integer, nullable=False),
    Column("owner_message_id", Integer, nullable=False),
    Column("owner_reply_text", Text, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("status", Text, nullable=False, default="pending"),
    Column("reason", Text),
    Column("created_at", Text, nullable=False),
    Column("resolved_at", Text),
    Index("idx_owner_reply_pairs_status_created", "status", "created_at"),
)

learning_proposals = Table(
    "learning_proposals",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("kind", Text, nullable=False),
    Column("payload", Text, nullable=False),
    Column("evidence", Text, nullable=False),
    Column("status", Text, nullable=False, default="pending"),
    Column("applied_reference", Text),
    Column("created_at", Text, nullable=False),
    Column("resolved_at", Text),
    Index("idx_learning_proposals_status_created", "status", "created_at"),
)

background_jobs = Table(
    "background_jobs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_type", Text, nullable=False),
    # JSON payload. Store references/IDs rather than message bodies where possible.
    Column("payload", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False, unique=True),
    # "pending" | "running" | "completed" | "dead"
    Column("status", Text, nullable=False, default="pending"),
    Column("attempts", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=3),
    Column("run_after", Text, nullable=False),
    Column("lease_owner", Text),
    Column("lease_expires_at", Text),
    Column("last_error", Text),
    Column("created_at", Text, nullable=False),
    Column("started_at", Text),
    Column("completed_at", Text),
    Index("idx_background_jobs_ready", "status", "run_after", "id"),
    Index("idx_background_jobs_lease", "status", "lease_expires_at"),
)

reply_decisions = Table(
    "reply_decisions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("intent", Text, nullable=False),
    Column("risk_level", Text, nullable=False),
    Column("memory_confidence", Text, nullable=False),
    Column("requires_owner_knowledge", Boolean, nullable=False),
    Column("requires_external_action", Boolean, nullable=False),
    Column("recommended_mode", Text, nullable=False),
    Column("actual_mode", Text, nullable=False),
    Column("reasons", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Index("idx_reply_decisions_created", "created_at"),
    Index("idx_reply_decisions_user_created", "user_id", "created_at"),
)

shadow_reviews = Table(
    "shadow_reviews",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("candidate_id", Text, nullable=False),
    Column("message_text", Text, nullable=False),
    Column("reply_a", Text),
    Column("reply_b", Text),
    Column("mapping", Text),
    Column("status", Text, nullable=False, default="queued"),
    Column("winner", Text),
    Column("error", Text),
    Column("created_at", Text, nullable=False),
    Column("resolved_at", Text),
    Index("idx_shadow_reviews_status_created", "status", "created_at"),
)

model_decision_reports = Table(
    "model_decision_reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("criteria_version", Text, nullable=False),
    Column("report", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Index("idx_model_decision_reports_created", "created_at"),
)

generation_runs = Table(
    "generation_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trace_id", Text, nullable=False, unique=True),
    Column("user_id", Integer),
    Column("suggestion_id", Integer),
    Column("purpose", Text, nullable=False),
    Column("provider", Text, nullable=False),
    Column("model", Text, nullable=False),
    Column("prompt_version", Text, nullable=False),
    Column("context_policy_version", Text, nullable=False),
    Column("response_id", Text),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cached_tokens", Integer),
    Column("latency_ms", Integer, nullable=False),
    Column("finish_reason", Text),
    Column("error_code", Text),
    Column("fallback_chain", Text),
    Column("created_at", Text, nullable=False),
    Index("idx_generation_runs_user_created", "user_id", "created_at"),
)

feedback_events = Table(
    "feedback_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("suggestion_id", Integer, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("reason", Text),
    Column("created_at", Text, nullable=False),
    Index("idx_feedback_events_suggestion", "suggestion_id", "created_at"),
)

suggestion_outcomes = Table(
    "suggestion_outcomes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("suggestion_id", Integer, nullable=False),
    Column("final_text", Text, nullable=False),
    Column("character_edit_distance", Integer, nullable=False),
    Column("token_edit_distance", Integer, nullable=False),
    Column("semantic_similarity", Float),
    Column("decision_seconds", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    Index("idx_suggestion_outcomes_suggestion", "suggestion_id"),
)

contact_examples = Table(
    "contact_examples",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    # An (contact message -> reply) pair, curated by the owner, injected into
    # the prompt as a few-shot guide for tone/format.
    # kind: "positive" = ideal reply to emulate; "negative" = bad reply to avoid.
    Column("contact_message", Text, nullable=False),
    Column("reply_text", Text, nullable=False),
    Column("kind", Text, nullable=False, default="positive"),
    Column("created_at", Text, nullable=False),
    Index("idx_contact_examples_user", "user_id"),
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

assistant_profiles = Table(
    "assistant_profiles",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("owner_id", Integer, nullable=False),
    Column("name", Text, nullable=False),
    Column("persona", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Index("idx_assistant_profiles_owner", "owner_id"),
    Index("uq_assistant_profiles_owner_name", "owner_id", "name", unique=True),
)

fact_categories = Table(
    "fact_categories",
    metadata,
    Column("key", Text, primary_key=True),
    Column("label", Text, nullable=False),
    # multi=True: the category holds a list of values (e.g. "любимое", interests);
    # the LLM appends to it and the owner manages items individually.
    Column("multi", Boolean, nullable=False, default=False),
    Column("created_at", Text, nullable=False),
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
