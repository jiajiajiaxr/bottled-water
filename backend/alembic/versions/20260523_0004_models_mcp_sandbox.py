"""model mcp sandbox remote tables

Revision ID: 20260523_0004
Revises: 20260523_0003
Create Date: 2026-05-23
"""
from __future__ import annotations

from typing import Sequence

from alembic import op

from app.core.database import Base
from app import models  # noqa: F401


revision: str = "20260523_0004"
down_revision: str | None = "20260523_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    for table_name in [
        "remote_connections",
        "sandbox_sessions",
        "mcp_servers",
        "model_configs",
        "model_providers",
    ]:
        op.drop_table(table_name)

