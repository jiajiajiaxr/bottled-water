"""conversation generation status

Revision ID: 20260601_0008
Revises: 20260523_0007
Create Date: 2026-06-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260601_0008"
down_revision = "20260523_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("generation_status", sa.String(20), nullable=False, server_default="idle"),
    )
    op.add_column(
        "conversations",
        sa.Column("active_session_id", sa.String(36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "active_session_id")
    op.drop_column("conversations", "generation_status")
