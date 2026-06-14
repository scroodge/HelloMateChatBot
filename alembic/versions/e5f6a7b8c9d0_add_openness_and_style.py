"""add openness, style learning, authored_by and contact_style_profiles (Phase 12)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-15 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(sa.Column("openness", sa.Text, nullable=True))
        batch_op.add_column(
            sa.Column(
                "style_learning_enabled",
                sa.Boolean,
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("conversation_messages") as batch_op:
        batch_op.add_column(sa.Column("authored_by", sa.Text, nullable=True))

    op.create_table(
        "contact_style_profiles",
        sa.Column("user_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("profile", sa.Text, nullable=False),
        sa.Column("covered_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("contact_style_profiles")
    with op.batch_alter_table("conversation_messages") as batch_op:
        batch_op.drop_column("authored_by")
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("style_learning_enabled")
        batch_op.drop_column("openness")
