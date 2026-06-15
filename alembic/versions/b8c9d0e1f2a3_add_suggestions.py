"""add suggestions (suggest inbox)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suggestions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("contact_message", sa.Text, nullable=False),
        sa.Column("draft_text", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("idx_suggestions_status_created", "suggestions", ["status", "created_at"])
    op.create_index("idx_suggestions_user", "suggestions", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_suggestions_user", table_name="suggestions")
    op.drop_index("idx_suggestions_status_created", table_name="suggestions")
    op.drop_table("suggestions")
