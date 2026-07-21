"""add_feedback_foundation

Revision ID: 112233aabbcc
Revises: f2a3b4c5d6e7
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "112233aabbcc"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.add_column(sa.Column("generation_trace_id", sa.Text(), nullable=True))
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.Text(), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer()),
        sa.Column("suggestion_id", sa.Integer()),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("context_policy_version", sa.Text(), nullable=False),
        sa.Column("response_id", sa.Text()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cached_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("finish_reason", sa.Text()),
        sa.Column("error_code", sa.Text()),
        sa.Column("fallback_chain", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_generation_runs_user_created", "generation_runs", ["user_id", "created_at"]
    )
    op.create_table(
        "feedback_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("suggestion_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_feedback_events_suggestion", "feedback_events", ["suggestion_id", "created_at"]
    )
    op.create_table(
        "suggestion_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("suggestion_id", sa.Integer(), nullable=False),
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column("character_edit_distance", sa.Integer(), nullable=False),
        sa.Column("token_edit_distance", sa.Integer(), nullable=False),
        sa.Column("semantic_similarity", sa.Float()),
        sa.Column("decision_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_suggestion_outcomes_suggestion", "suggestion_outcomes", ["suggestion_id"])


def downgrade() -> None:
    op.drop_index("idx_suggestion_outcomes_suggestion", table_name="suggestion_outcomes")
    op.drop_table("suggestion_outcomes")
    op.drop_index("idx_feedback_events_suggestion", table_name="feedback_events")
    op.drop_table("feedback_events")
    op.drop_index("idx_generation_runs_user_created", table_name="generation_runs")
    op.drop_table("generation_runs")
    with op.batch_alter_table("suggestions") as batch_op:
        batch_op.drop_column("generation_trace_id")
