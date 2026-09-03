"""Initial schema (immutable baseline).

Explicit Alembic operations for the baseline schema. This revision is
INTENTIONALLY frozen: it does NOT import the live model metadata, so a future
model change can never retroactively alter what migration 0001 creates. New
schema changes must be added as a separate revision (0002, …).

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "subject", name="uq_provider_subject"),
    )
    op.create_index("ix_users_subject", "users", ["subject"])

    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_interviews_user_id", "interviews", ["user_id"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("canonical_question", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=64), nullable=True),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("timing_guidance", sa.JSON(), nullable=True),
        sa.Column("is_deep_dive", sa.Boolean(), nullable=False),
        sa.Column("parent_position", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_questions_interview_id", "questions", ["interview_id"])

    op.create_table(
        "answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evaluation", sa.JSON(), nullable=True),
        sa.Column("timing_metrics", sa.JSON(), nullable=True),
        sa.Column("visual_metrics", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_answers_question_id", "answers", ["question_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reports_interview_id", "reports", ["interview_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_interview_id", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_answers_question_id", table_name="answers")
    op.drop_table("answers")
    op.drop_index("ix_questions_interview_id", table_name="questions")
    op.drop_table("questions")
    op.drop_index("ix_interviews_user_id", table_name="interviews")
    op.drop_table("interviews")
    op.drop_index("ix_users_subject", table_name="users")
    op.drop_table("users")
