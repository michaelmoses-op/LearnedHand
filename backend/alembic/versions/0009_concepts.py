"""concepts and concept_mentions; 'concepts' ingest stage

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

RLS_TABLES = ["concepts", "concept_mentions"]
OLD = "('parse', 'sections', 'chunk', 'context', 'embed', 'summaries', 'validate')"
NEW = "('parse', 'sections', 'chunk', 'context', 'embed', 'summaries', 'concepts', 'validate')"


def _fk(table: str, col: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [col],
        [f"{target}.id"],
        name=op.f(f"fk_{table}_{col}_{target}"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.drop_constraint(op.f("ck_documents_ingest_stage"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_ingest_stage"),
        "documents",
        f"ingest_stage is null or ingest_stage in {NEW}",
    )
    op.create_table(
        "concepts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("first_ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("first_ordinal >= 0", name=op.f("ck_concepts_first_ordinal_nonneg")),
        _fk("concepts", "document_id", "documents"),
        _fk("concepts", "user_id", "users"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concepts")),
    )
    op.create_index(op.f("ix_concepts_user_id"), "concepts", ["user_id"])
    op.create_index(op.f("ix_concepts_document_id"), "concepts", ["document_id"])
    op.create_index("uq_concepts_document_key", "concepts", ["document_id", "key"], unique=True)

    op.create_table(
        "concept_mentions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("concept_id", sa.UUID(), nullable=False),
        sa.Column("section_id", sa.UUID(), nullable=False),
        sa.Column("first_ordinal", sa.Integer(), nullable=False),
        sa.Column("last_ordinal", sa.Integer(), nullable=False),
        sa.Column("section_last_ordinal", sa.Integer(), nullable=False),
        sa.Column("mention_chunks", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "first_ordinal >= 0", name=op.f("ck_concept_mentions_first_ordinal_nonneg")
        ),
        sa.CheckConstraint(
            "last_ordinal >= first_ordinal", name=op.f("ck_concept_mentions_last_gte_first")
        ),
        sa.CheckConstraint(
            "mention_chunks >= 0", name=op.f("ck_concept_mentions_mention_chunks_nonneg")
        ),
        _fk("concept_mentions", "concept_id", "concepts"),
        _fk("concept_mentions", "document_id", "documents"),
        _fk("concept_mentions", "section_id", "sections"),
        _fk("concept_mentions", "user_id", "users"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_mentions")),
    )
    for col in ("user_id", "document_id", "concept_id", "section_id"):
        op.create_index(op.f(f"ix_concept_mentions_{col}"), "concept_mentions", [col])

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
    op.drop_table("concept_mentions")
    op.drop_table("concepts")
    # FORCE RLS would make the owner's UPDATE match 0 rows; lift it around the fix-up.
    op.execute("ALTER TABLE documents NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE documents SET ingest_stage = 'summaries' WHERE ingest_stage = 'concepts'")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY")
    op.drop_constraint(op.f("ck_documents_ingest_stage"), "documents", type_="check")
    op.create_check_constraint(
        op.f("ck_documents_ingest_stage"),
        "documents",
        f"ingest_stage is null or ingest_stage in {OLD}",
    )
