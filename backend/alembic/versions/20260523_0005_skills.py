"""skill management table

Revision ID: 20260523_0005
Revises: 20260523_0004
Create Date: 2026-05-23
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from app import models  # noqa: F401
from app.core.database import Base


revision: str = "20260523_0005"
down_revision: str | None = "20260523_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    op.drop_table("skills")
