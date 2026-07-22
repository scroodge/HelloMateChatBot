"""add shadow reviews

Revision ID: 8899aabbccdd
Revises: 778899aabbcc
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "8899aabbccdd"
down_revision = "778899aabbcc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shadow_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Text(), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("reply_a", sa.Text()), sa.Column("reply_b", sa.Text()),
        sa.Column("mapping", sa.Text()), sa.Column("status", sa.Text(), nullable=False),
        sa.Column("winner", sa.Text()), sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False), sa.Column("resolved_at", sa.Text()),
    )
    op.create_index("idx_shadow_reviews_status_created", "shadow_reviews", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_shadow_reviews_status_created", table_name="shadow_reviews")
    op.drop_table("shadow_reviews")
