"""drop flashcards and quiz_questions (feature removed)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

RLS_TABLES = ["flashcards", "quiz_questions"]


def _fk(table: str, col: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [col], [f"{target}.id"], name=op.f(f"fk_{table}_{col}_{target}"), ondelete="CASCADE"
    )


def _base() -> list[sa.Column]:  # type: ignore[type-arg]
    return [
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
    ]


def _now(name: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=None if nullable else sa.text("now()"),
        nullable=nullable,
    )


def upgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
    op.drop_table("quiz_questions")
    op.drop_table("flashcards")


def downgrade() -> None:
    op.create_table(
        "flashcards",
        *_base(),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("front_key", sa.String(length=200), nullable=False),
        sa.Column("source_ordinal", sa.Integer(), nullable=False),
        sa.Column("ease", sa.Float(), server_default=sa.text("2.5"), nullable=False),
        sa.Column("interval_days", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reps", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("lapses", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _now("due_at"),
        _now("last_reviewed_at", nullable=True),
        _now("created_at"),
        sa.CheckConstraint("source_ordinal >= 0", name=op.f("ck_flashcards_source_nonneg")),
        sa.CheckConstraint("reps >= 0 and lapses >= 0", name=op.f("ck_flashcards_counters_nonneg")),
        _fk("flashcards", "document_id", "documents"),
        _fk("flashcards", "user_id", "users"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flashcards")),
    )
    op.create_index(op.f("ix_flashcards_user_id"), "flashcards", ["user_id"])
    op.create_index(op.f("ix_flashcards_document_id"), "flashcards", ["document_id"])
    op.create_index("ix_flashcards_document_due", "flashcards", ["document_id", "due_at"])
    op.create_table(
        "quiz_questions",
        *_base(),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_key", sa.String(length=200), nullable=False),
        sa.Column("choices", postgresql.JSONB(), nullable=False),
        sa.Column("answer_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("source_ordinal", sa.Integer(), nullable=False),
        sa.Column("times_answered", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("times_correct", sa.Integer(), server_default=sa.text("0"), nullable=False),
        _now("created_at"),
        sa.CheckConstraint("source_ordinal >= 0", name=op.f("ck_quiz_questions_source_nonneg")),
        sa.CheckConstraint("answer_index >= 0", name=op.f("ck_quiz_questions_answer_nonneg")),
        sa.CheckConstraint(
            "times_correct <= times_answered", name=op.f("ck_quiz_questions_correct_le_answered")
        ),
        _fk("quiz_questions", "document_id", "documents"),
        _fk("quiz_questions", "user_id", "users"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_questions")),
    )
    op.create_index(op.f("ix_quiz_questions_user_id"), "quiz_questions", ["user_id"])
    op.create_index(op.f("ix_quiz_questions_document_id"), "quiz_questions", ["document_id"])
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_owner ON {table} "
            "USING (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid) "
            "WITH CHECK (user_id = nullif(current_setting('app.current_user_id', true), '')::uuid)"
        )
