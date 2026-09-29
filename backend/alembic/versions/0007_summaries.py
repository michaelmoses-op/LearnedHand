"""summaries, section chunk ranges, plain embeddings, page numbers, quality report, stage versions

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.ingestion.constants import EMBEDDING_DIMENSION

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

OLD_STAGES = "('parse', 'sections', 'chunk', 'context', 'embed')"
NEW_STAGES = "('parse', 'sections', 'chunk', 'context', 'embed', 'summaries', 'validate')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_documents_ingest_stage"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_ingest_stage"),
        "documents",
        f"ingest_stage is null or ingest_stage in {NEW_STAGES}",
    )
    op.add_column(
        "documents",
        sa.Column(
            "stage_versions",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("documents", sa.Column("quality_report", postgresql.JSONB(), nullable=True))

    for col in ("first_chunk_ordinal", "last_chunk_ordinal", "page_start", "page_end"):
        op.add_column("sections", sa.Column(col, sa.Integer(), nullable=True))
    op.add_column("sections", sa.Column("page_map", postgresql.JSONB(), nullable=True))
    op.add_column("chunks", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("page_end", sa.Integer(), nullable=True))
    op.add_column(
        "chunks", sa.Column("embedding_plain", Vector(EMBEDDING_DIMENSION), nullable=True)
    )
    op.execute(
        "CREATE INDEX ix_chunks_embedding_plain_hnsw ON chunks "
        "USING hnsw (embedding_plain vector_cosine_ops)"
    )

    op.create_table(
        "summaries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("section_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("depth", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("first_ordinal", sa.Integer(), nullable=False),
        sa.Column("last_ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("kind in ('section', 'book')", name=op.f("ck_summaries_kind")),
        sa.CheckConstraint("first_ordinal >= 0", name=op.f("ck_summaries_first_ordinal_nonneg")),
        sa.CheckConstraint(
            "last_ordinal >= first_ordinal", name=op.f("ck_summaries_last_gte_first")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_summaries_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name=op.f("fk_summaries_section_id_sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_summaries_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_summaries")),
    )
    op.create_index(op.f("ix_summaries_document_id"), "summaries", ["document_id"])
    op.create_index(op.f("ix_summaries_section_id"), "summaries", ["section_id"])
    op.create_index(op.f("ix_summaries_user_id"), "summaries", ["user_id"])
    op.create_index("ix_summaries_document_kind", "summaries", ["document_id", "kind"])
    op.execute(
        "CREATE INDEX ix_summaries_embedding_hnsw ON summaries "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("ALTER TABLE summaries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE summaries FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY summaries_owner ON summaries "
        "USING (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS summaries_owner ON summaries")
    op.execute("DROP INDEX IF EXISTS ix_summaries_embedding_hnsw")
    op.drop_index("ix_summaries_document_kind", table_name="summaries")
    op.drop_index(op.f("ix_summaries_user_id"), table_name="summaries")
    op.drop_index(op.f("ix_summaries_section_id"), table_name="summaries")
    op.drop_index(op.f("ix_summaries_document_id"), table_name="summaries")
    op.drop_table("summaries")

    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_plain_hnsw")
    op.drop_column("chunks", "embedding_plain")
    op.drop_column("chunks", "page_end")
    op.drop_column("chunks", "page_start")
    op.drop_column("sections", "page_map")
    for col in ("page_end", "page_start", "last_chunk_ordinal", "first_chunk_ordinal"):
        op.drop_column("sections", col)
    op.drop_column("documents", "quality_report")
    op.drop_column("documents", "stage_versions")

    # FORCE RLS would make the owner's UPDATE match 0 rows; lift it around the fix-up.
    op.execute("ALTER TABLE documents NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE documents SET ingest_stage = 'embed' "
        "WHERE ingest_stage IN ('summaries', 'validate')"
    )
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_documents_ingest_stage"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_ingest_stage"),
        "documents",
        f"ingest_stage is null or ingest_stage in {OLD_STAGES}",
    )
