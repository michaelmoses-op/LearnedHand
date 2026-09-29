"""baseline: required extensions

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # setup_db.sh already creates these; IF NOT EXISTS keeps this idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    # Extensions are shared infrastructure; intentionally left in place.
    pass
