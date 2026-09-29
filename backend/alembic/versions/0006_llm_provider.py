"""real-provider support: 1536-d embeddings, embedding model tracking, llm_calls detail

Revision ID: 0006
Revises: 0005

Note: tables have FORCE ROW LEVEL SECURITY, so a plain UPDATE run as the owner with no user
context matches zero rows. This migration therefore uses DDL for vectors and briefly lifts
FORCE around the one data fix-up that has to touch every user's rows.
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _replace_embedding_column(dim: int) -> None:
    # Vectors of a different width cannot be cast, so drop and re-add (also drops the index).
    op.execute("ALTER TABLE chunks DROP COLUMN embedding")
    op.execute(f"ALTER TABLE chunks ADD COLUMN embedding vector({dim})")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )


def _mark_documents_for_reingest() -> None:
    op.execute("ALTER TABLE documents NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE documents SET status = 'uploaded', ingest_stage = NULL "
        "WHERE status IN ('ready', 'processing')"
    )
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.add_column("chunks", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("chunks", sa.Column("embedding_dim", sa.Integer(), nullable=True))
    _replace_embedding_column(1536)
    # Their vectors are gone: they need re-ingesting (POST /documents/{id}/reingest).
    _mark_documents_for_reingest()
    op.add_column(
        "llm_calls",
        sa.Column("cached_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("llm_calls", sa.Column("stage", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("llm_calls", "stage")
    op.drop_column("llm_calls", "cached_tokens")
    _replace_embedding_column(32)
    _mark_documents_for_reingest()
    op.drop_column("chunks", "embedding_dim")
    op.drop_column("chunks", "embedding_model")
