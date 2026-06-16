"""add multi flag to fact_categories

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fact_categories") as batch_op:
        batch_op.add_column(
            sa.Column("multi", sa.Boolean, nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("fact_categories") as batch_op:
        batch_op.drop_column("multi")
