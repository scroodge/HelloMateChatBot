"""add message embeddings for semantic recall (Phase 13)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_message_embeddings",
        sa.Column("message_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("embedding", sa.LargeBinary, nullable=False),
    )
    op.create_index(
        "idx_message_embeddings_user",
        "conversation_message_embeddings",
        ["user_id"],
    )

    op.create_table(
        "recall_index_meta",
        sa.Column("user_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("watermark_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recall_index_meta")
    op.drop_index("idx_message_embeddings_user", table_name="conversation_message_embeddings")
    op.drop_table("conversation_message_embeddings")
