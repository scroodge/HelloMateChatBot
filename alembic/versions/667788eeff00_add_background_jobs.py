"""add durable background jobs

Revision ID: 667788eeff00
Revises: 556677ddeeff
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "667788eeff00"
down_revision = "556677ddeeff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.Text(), nullable=False),
        sa.Column("lease_owner", sa.Text()),
        sa.Column("lease_expires_at", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text()),
        sa.Column("completed_at", sa.Text()),
    )
    op.create_index("idx_background_jobs_ready", "background_jobs", ["status", "run_after", "id"])
    op.create_index("idx_background_jobs_lease", "background_jobs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("idx_background_jobs_lease", table_name="background_jobs")
    op.drop_index("idx_background_jobs_ready", table_name="background_jobs")
    op.drop_table("background_jobs")
