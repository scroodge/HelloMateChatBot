"""add assistant_profiles (owner personal assistant)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("persona", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
    )
    op.create_index("idx_assistant_profiles_owner", "assistant_profiles", ["owner_id"])
    op.create_index(
        "uq_assistant_profiles_owner_name",
        "assistant_profiles",
        ["owner_id", "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_assistant_profiles_owner_name", table_name="assistant_profiles")
    op.drop_index("idx_assistant_profiles_owner", table_name="assistant_profiles")
    op.drop_table("assistant_profiles")
