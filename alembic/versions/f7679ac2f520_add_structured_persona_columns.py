"""add_structured_persona_columns

Revision ID: f7679ac2f520
Revises: e6998c8fc9ec
Create Date: 2026-06-14

Adds structured persona fields to user_settings so the admin console can build
personas without requiring the owner to write raw system prompts.
"""

import sqlalchemy as sa
from alembic import op

revision = "f7679ac2f520"
down_revision = "e6998c8fc9ec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(sa.Column("persona_preset", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("persona_relationship", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("persona_tone", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("persona_topics", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("persona_boundaries", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("persona_boundaries")
        batch_op.drop_column("persona_topics")
        batch_op.drop_column("persona_tone")
        batch_op.drop_column("persona_relationship")
        batch_op.drop_column("persona_preset")
