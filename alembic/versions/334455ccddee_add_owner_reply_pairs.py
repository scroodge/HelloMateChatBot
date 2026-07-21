"""add owner reply pairs

Revision ID: 334455ccddee
Revises: 223344bbccdd
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "334455ccddee"
down_revision = "223344bbccdd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_reply_pairs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("suggestion_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("owner_message_id", sa.Integer(), nullable=False),
        sa.Column("owner_reply_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text()),
    )
    op.create_index(
        "idx_owner_reply_pairs_status_created",
        "owner_reply_pairs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_owner_reply_pairs_status_created", table_name="owner_reply_pairs")
    op.drop_table("owner_reply_pairs")
