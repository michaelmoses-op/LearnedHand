"""eval_runs and eval_results (metrics only, under RLS)

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

RLS_TABLES = ["eval_runs", "eval_results"]


def upgrade() -> None:
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("config_name", sa.String(length=100), nullable=False),
        sa.Column("corpus", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_eval_runs_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_eval_runs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    op.create_index(op.f("ix_eval_runs_user_id"), "eval_runs", ["user_id"])
    op.create_index(op.f("ix_eval_runs_batch_id"), "eval_runs", ["batch_id"])

    op.create_table(
        "eval_results",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("question_id", sa.String(length=100), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("stages", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["eval_runs.id"],
            name=op.f("fk_eval_results_run_id_eval_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_eval_results_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_results")),
    )
    op.create_index(op.f("ix_eval_results_user_id"), "eval_results", ["user_id"])
    op.create_index(op.f("ix_eval_results_run_id"), "eval_results", ["run_id"])

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
    op.drop_index(op.f("ix_eval_results_run_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_user_id"), table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_index(op.f("ix_eval_runs_batch_id"), table_name="eval_runs")
    op.drop_index(op.f("ix_eval_runs_user_id"), table_name="eval_runs")
    op.drop_table("eval_runs")
