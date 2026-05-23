"""tool catalog

Revision ID: 20260523_0007
Revises: 20260523_0006
Create Date: 2026-05-23
"""

from __future__ import annotations

from alembic import op


revision = "20260523_0007"
down_revision = "20260523_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.core.database import Base
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_table("tool_definitions")
