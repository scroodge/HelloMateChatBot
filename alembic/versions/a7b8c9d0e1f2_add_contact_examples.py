"""add per-contact few-shot examples

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_examples",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("contact_message", sa.Text, nullable=False),
        sa.Column("reply_text", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("idx_contact_examples_user", "contact_examples", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_contact_examples_user", table_name="contact_examples")
    op.drop_table("contact_examples")
