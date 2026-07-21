"""add learning proposals

Revision ID: 556677ddeeff
Revises: 445566ddeeff
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "556677ddeeff"
down_revision = "445566ddeeff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("learning_proposals", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True), sa.Column("user_id", sa.Integer(), nullable=False), sa.Column("kind", sa.Text(), nullable=False), sa.Column("payload", sa.Text(), nullable=False), sa.Column("evidence", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False), sa.Column("applied_reference", sa.Text()), sa.Column("created_at", sa.Text(), nullable=False), sa.Column("resolved_at", sa.Text()))
    op.create_index("idx_learning_proposals_status_created", "learning_proposals", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_learning_proposals_status_created", table_name="learning_proposals")
    op.drop_table("learning_proposals")
