"""add kind column to contact_examples

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op  # noqa: F401 (imported for side-effects)

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contact_examples") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.Text, nullable=False, server_default="positive")
        )


def downgrade() -> None:
    with op.batch_alter_table("contact_examples") as batch_op:
        batch_op.drop_column("kind")
