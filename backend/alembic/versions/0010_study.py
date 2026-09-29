"""notes/highlights, flashcards and quiz questions

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

RLS_TABLES = ["notes", "flashcards", "quiz_questions"]


def _fk(table: str, col: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [col], [f"{target}.id"], name=op.f(f"fk_{table}_{col}_{target}"), ondelete="CASCADE"
    )


def _base(table: str) -> list[sa.Column]:  # type: ignore[type-arg]
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


def _finish(table: str) -> None:
    op.create_index(op.f(f"ix_{table}_user_id"), table, ["user_id"])
    op.create_index(op.f(f"ix_{table}_document_id"), table, ["document_id"])


def upgrade() -> None:
    op.create_table(
        "notes",
        *_base("notes"),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("anchor_ordinal", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(body, '') || ' ' || coalesce(quote, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint("kind in ('note', 'highlight')", name=op.f("ck_notes_kind_valid")),
        sa.CheckConstraint("anchor_ordinal >= 0", name=op.f("ck_notes_anchor_nonneg")),
        sa.CheckConstraint(
            "kind <> 'highlight' or quote is not null", name=op.f("ck_notes_highlight_has_quote")
        ),
        _fk("notes", "document_id", "documents"),
        _fk("notes", "user_id", "users"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    _finish("notes")
    op.execute("CREATE INDEX ix_notes_search_vector ON notes USING gin (search_vector)")

    op.create_table(
        "flashcards",
        *_base("flashcards"),
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
    _finish("flashcards")
    op.create_index("ix_flashcards_document_due", "flashcards", ["document_id", "due_at"])

    op.create_table(
        "quiz_questions",
        *_base("quiz_questions"),
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
    _finish("quiz_questions")

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
    op.drop_table("quiz_questions")
    op.drop_table("flashcards")
    op.drop_table("notes")
