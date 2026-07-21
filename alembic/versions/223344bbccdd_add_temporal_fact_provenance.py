"""add temporal fact provenance

Revision ID: 223344bbccdd
Revises: 112233aabbcc
Create Date: 2026-07-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "223344bbccdd"
down_revision = "112233aabbcc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contact_facts") as batch_op:
        batch_op.add_column(sa.Column("source_message_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("confidence", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("first_observed_at", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_observed_at", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("valid_from", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("valid_until", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("owner_confirmed", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("version_id", sa.Text(), nullable=True))
    op.create_table(
        "contact_fact_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.Integer()),
        sa.Column("confidence", sa.Float()),
        sa.Column("first_observed_at", sa.Text()),
        sa.Column("last_observed_at", sa.Text()),
        sa.Column("valid_from", sa.Text()),
        sa.Column("valid_until", sa.Text()),
        sa.Column("owner_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version_id", sa.Text()),
        sa.Column("superseded_by", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_contact_fact_history_user_key",
        "contact_fact_history",
        ["user_id", "key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_contact_fact_history_user_key", table_name="contact_fact_history")
    op.drop_table("contact_fact_history")
    with op.batch_alter_table("contact_facts") as batch_op:
        batch_op.drop_column("version_id")
        batch_op.drop_column("owner_confirmed")
        batch_op.drop_column("valid_until")
        batch_op.drop_column("valid_from")
        batch_op.drop_column("last_observed_at")
        batch_op.drop_column("first_observed_at")
        batch_op.drop_column("confidence")
        batch_op.drop_column("source_message_id")
