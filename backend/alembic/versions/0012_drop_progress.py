"""drop document_progress (reading-position gating removed); notes anchor becomes optional

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS document_progress_owner ON document_progress")
    op.drop_index(op.f("ix_document_progress_user_id"), table_name="document_progress")
    op.drop_index(op.f("ix_document_progress_document_id"), table_name="document_progress")
    op.drop_table("document_progress")
    op.alter_column("notes", "anchor_ordinal", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # FORCE RLS would make the owner's UPDATE match 0 rows; lift it around the fix-up.
    op.execute("ALTER TABLE notes NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE notes SET anchor_ordinal = 0 WHERE anchor_ordinal IS NULL")
    op.execute("ALTER TABLE notes FORCE ROW LEVEL SECURITY")
    op.alter_column("notes", "anchor_ordinal", existing_type=sa.Integer(), nullable=False)
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
    op.create_index(op.f("ix_document_progress_document_id"), "document_progress", ["document_id"])
    op.create_index(op.f("ix_document_progress_user_id"), "document_progress", ["user_id"])
    op.execute("ALTER TABLE document_progress ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_progress FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY document_progress_owner ON document_progress "
        "USING (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid)"
    )
