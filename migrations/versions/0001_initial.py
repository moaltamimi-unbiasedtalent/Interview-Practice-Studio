"""Initial schema (baseline).

Creates the full schema from the app's SQLAlchemy models. Using the model
metadata keeps this baseline revision in exact sync with the ORM; subsequent
schema changes should be generated with ``alembic revision --autogenerate``.

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01
"""

from __future__ import annotations

from alembic import op

from src.persistence import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
