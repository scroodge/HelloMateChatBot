"""add contact_facts and contact_facts_meta tables (Phase 11)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-14 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_facts",
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text, nullable=False),
    )
    op.create_index("pk_contact_facts", "contact_facts", ["user_id", "key"], unique=True)

    op.create_table(
        "contact_facts_meta",
        sa.Column("user_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("last_message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("contact_facts_meta")
    op.drop_index("pk_contact_facts", "contact_facts")
    op.drop_table("contact_facts")
