"""ingestion tables: sections, chunks, document_progress; document.ingest_stage

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.ingestion.constants import EMBEDDING_DIMENSION

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

RLS_TABLES = ["sections", "chunks", "document_progress"]


def upgrade() -> None:
    op.add_column("documents", sa.Column("ingest_stage", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        op.f("ck_documents_ingest_stage"),
        "documents",
        "ingest_stage is null or ingest_stage in "
        "('parse', 'sections', 'chunk', 'context', 'embed')",
    )

    op.create_table(
        "sections",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("spine_href", sa.String(length=1000), nullable=False),
        sa.Column("text", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("depth >= 0", name=op.f("ck_sections_depth_nonneg")),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_sections_ordinal_nonneg")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_sections_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["sections.id"],
            name=op.f("fk_sections_parent_id_sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sections_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
        sa.UniqueConstraint("document_id", "ordinal", name=op.f("uq_sections_document_ordinal")),
    )
    op.create_index(op.f("ix_sections_document_id"), "sections", ["document_id"], unique=False)
    op.create_index(op.f("ix_sections_parent_id"), "sections", ["parent_id"], unique=False)
    op.create_index(op.f("ix_sections_user_id"), "sections", ["user_id"], unique=False)

    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("section_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context_prefix", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("char_start", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("char_end", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(context_prefix, '') || ' ' || coalesce(text, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("char_end >= char_start", name=op.f("ck_chunks_char_end_gte_start")),
        sa.CheckConstraint("char_start >= 0", name=op.f("ck_chunks_char_start_nonneg")),
        sa.CheckConstraint("ordinal >= 0", name=op.f("ck_chunks_ordinal_nonneg")),
        sa.CheckConstraint("token_count >= 0", name=op.f("ck_chunks_token_count_nonneg")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name=op.f("fk_chunks_section_id_sections"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_chunks_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint("document_id", "ordinal", name=op.f("uq_chunks_document_ordinal")),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_chunks_section_id"), "chunks", ["section_id"], unique=False)
    op.create_index(op.f("ix_chunks_user_id"), "chunks", ["user_id"], unique=False)
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_chunks_search_vector ON chunks USING gin (search_vector)")

    op.create_table(
        "document_progress",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("max_ordinal", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "max_ordinal >= 0", name=op.f("ck_document_progress_max_ordinal_nonneg")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_progress_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_document_progress_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_progress")),
        sa.UniqueConstraint(
            "user_id", "document_id", name=op.f("uq_document_progress_user_document")
        ),
    )
    op.create_index(
        op.f("ix_document_progress_document_id"), "document_progress", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_document_progress_user_id"), "document_progress", ["user_id"], unique=False
    )

    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} "
            "USING (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid) "
            "WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
    op.drop_index(op.f("ix_document_progress_user_id"), table_name="document_progress")
    op.drop_index(op.f("ix_document_progress_document_id"), table_name="document_progress")
    op.drop_table("document_progress")
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_vector")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_index(op.f("ix_chunks_user_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_section_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_sections_user_id"), table_name="sections")
    op.drop_index(op.f("ix_sections_parent_id"), table_name="sections")
    op.drop_index(op.f("ix_sections_document_id"), table_name="sections")
    op.drop_table("sections")
    op.drop_constraint(op.f("ck_documents_ingest_stage"), "documents", type_="check")
    op.drop_column("documents", "ingest_stage")
