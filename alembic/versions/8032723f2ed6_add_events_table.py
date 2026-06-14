"""add_events_table

Revision ID: 8032723f2ed6
Revises: f7679ac2f520
Create Date: 2026-06-14

Adds the events table for usage tracking and admin stats.
"""

import sqlalchemy as sa
from alembic import op

revision = "8032723f2ed6"
down_revision = "f7679ac2f520"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("events") as batch_op:
        batch_op.create_index("idx_events_user_created", ["user_id", "created_at"])
        batch_op.create_index("idx_events_type_created", ["event_type", "created_at"])


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_index("idx_events_type_created")
        batch_op.drop_index("idx_events_user_created")
    op.drop_table("events")
