"""Phase 6: Alembic baseline migration produces the expected schema.

Skipped when alembic is not installed (it ships in the optional [db] extra).
Runs the immutable 0001 baseline against a throwaway SQLite database and checks
the tables/indexes it creates, then that downgrade removes them.
"""

from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("alembic") is None,
    reason="alembic not installed (pip install -e \".[db]\")",
)

_EXPECTED_TABLES = {"users", "interviews", "questions", "answers", "reports"}
_EXPECTED_INDEXES = {
    "ix_users_subject", "ix_interviews_user_id", "ix_questions_interview_id",
    "ix_answers_question_id", "ix_reports_interview_id",
}


def _alembic_config(db_url: str):
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_head_creates_baseline_schema(tmp_path, monkeypatch):
    from alembic import command
    from sqlalchemy import create_engine, inspect

    db_url = f"sqlite:///{tmp_path/'m.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)  # env.py reads this
    command.upgrade(_alembic_config(db_url), "head")

    insp = inspect(create_engine(db_url))
    tables = set(insp.get_table_names())
    assert _EXPECTED_TABLES <= tables
    indexes = {ix["name"] for t in _EXPECTED_TABLES for ix in insp.get_indexes(t)}
    assert _EXPECTED_INDEXES <= indexes


def test_downgrade_base_removes_schema(tmp_path, monkeypatch):
    from alembic import command
    from sqlalchemy import create_engine, inspect

    db_url = f"sqlite:///{tmp_path/'m.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    tables = set(inspect(create_engine(db_url)).get_table_names())
    assert not (_EXPECTED_TABLES & tables)  # all baseline tables dropped


def test_baseline_migration_does_not_import_live_metadata():
    # The baseline must be immutable: it must NOT create the schema from the live
    # model metadata (which would let later model edits mutate migration 0001).
    from pathlib import Path

    source = Path("migrations/versions/0001_initial.py").read_text()
    assert "metadata.create_all" not in source
    assert "op.create_table" in source
