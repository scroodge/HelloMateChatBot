"""baseline

Revision ID: e6998c8fc9ec
Revises:
Create Date: 2026-06-14

No-op baseline. The schema was already provisioned by Database.open() → create_all().
This revision just lets Alembic track incremental changes from here onward.

To stamp an existing database without running any DDL:
    alembic stamp e6998c8fc9ec
"""

revision = "e6998c8fc9ec"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
