"""add shadow reply decisions

Revision ID: 778899aabbcc
Revises: 667788eeff00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "778899aabbcc"
down_revision = "667788eeff00"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reply_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("memory_confidence", sa.Text(), nullable=False),
        sa.Column("requires_owner_knowledge", sa.Boolean(), nullable=False),
        sa.Column("requires_external_action", sa.Boolean(), nullable=False),
        sa.Column("recommended_mode", sa.Text(), nullable=False),
        sa.Column("actual_mode", sa.Text(), nullable=False),
        sa.Column("reasons", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_reply_decisions_created", "reply_decisions", ["created_at"])
    op.create_index(
        "idx_reply_decisions_user_created", "reply_decisions", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_reply_decisions_user_created", table_name="reply_decisions")
    op.drop_index("idx_reply_decisions_created", table_name="reply_decisions")
    op.drop_table("reply_decisions")
