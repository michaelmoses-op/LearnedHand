"""llm_calls accounting (FORCE RLS)

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'ok'"), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("input_tokens >= 0", name=op.f("ck_llm_calls_input_tokens_nonneg")),
        sa.CheckConstraint(
            "kind in ('complete', 'stream', 'embed')", name=op.f("ck_llm_calls_kind")
        ),
        sa.CheckConstraint("latency_ms >= 0", name=op.f("ck_llm_calls_latency_ms_nonneg")),
        sa.CheckConstraint("output_tokens >= 0", name=op.f("ck_llm_calls_output_tokens_nonneg")),
        sa.CheckConstraint("status in ('ok', 'error')", name=op.f("ck_llm_calls_status")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_llm_calls_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_llm_calls_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_index(op.f("ix_llm_calls_document_id"), "llm_calls", ["document_id"], unique=False)
    op.create_index(op.f("ix_llm_calls_user_id"), "llm_calls", ["user_id"], unique=False)

    op.execute("ALTER TABLE llm_calls ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE llm_calls FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY llm_calls_owner ON llm_calls "
        "USING (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid) "
        "WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS llm_calls_owner ON llm_calls")
    op.drop_index(op.f("ix_llm_calls_user_id"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_document_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
