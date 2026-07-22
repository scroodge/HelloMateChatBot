"""add model decision reports

Revision ID: 99aabbccdde0
Revises: 8899aabbccdd
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "99aabbccdde0"
down_revision = "8899aabbccdd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_decision_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("criteria_version", sa.Text(), nullable=False),
        sa.Column("report", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_model_decision_reports_created", "model_decision_reports", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_model_decision_reports_created", table_name="model_decision_reports")
    op.drop_table("model_decision_reports")
