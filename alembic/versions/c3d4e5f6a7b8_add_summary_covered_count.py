"""add_summary_covered_count

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-14

Adds covered_count to conversation_summaries — how many of the oldest messages
are already folded into the rolling summary (Phase 10).
"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversation_summaries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "covered_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("conversation_summaries") as batch_op:
        batch_op.drop_column("covered_count")
