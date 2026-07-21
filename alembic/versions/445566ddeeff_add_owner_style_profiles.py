"""add owner style profiles

Revision ID: 445566ddeeff
Revises: 334455ccddee
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "445566ddeeff"
down_revision = "334455ccddee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "owner_style_profiles",
        sa.Column("scope_key", sa.Text(), primary_key=True),
        sa.Column("profile", sa.Text(), nullable=False),
        sa.Column("covered_through_message_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("owner_style_profiles")
