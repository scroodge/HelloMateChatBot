"""add_business_tables

Revision ID: a1b2c3d4e5f6
Revises: 8032723f2ed6
Create Date: 2026-06-14

Adds tables for Telegram Business connections and managed chats.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "8032723f2ed6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_connections",
        sa.Column("connection_id", sa.Text(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "idx_business_connections_owner",
        "business_connections",
        ["owner_user_id"],
    )

    op.create_table(
        "business_chats",
        sa.Column("chat_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("contact_user_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_business_chats_contact", "business_chats", ["contact_user_id"])
    op.create_index("idx_business_chats_connection", "business_chats", ["connection_id"])


def downgrade() -> None:
    op.drop_index("idx_business_chats_connection", table_name="business_chats")
    op.drop_index("idx_business_chats_contact", table_name="business_chats")
    op.drop_table("business_chats")
    op.drop_index("idx_business_connections_owner", table_name="business_connections")
    op.drop_table("business_connections")
