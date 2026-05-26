"""capability runtime catalog boundaries

Revision ID: 20260523_0008
Revises: 20260523_0007
Create Date: 2026-05-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260523_0008"
down_revision = "20260523_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _add_tool_definition_columns(inspector)
    if "tool_invocations" not in inspector.get_table_names():
        _create_tool_invocations()
    if "skill_runs" not in inspector.get_table_names():
        _create_skill_runs()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_table("tool_invocations")
        op.drop_table("skill_runs")
        op.drop_column("tool_definitions", "builtin_handler")
        op.drop_column("tool_definitions", "is_builtin")


def _add_tool_definition_columns(inspector) -> None:
    columns = {column["name"] for column in inspector.get_columns("tool_definitions")}
    if "is_builtin" not in columns:
        op.add_column(
            "tool_definitions",
            sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_tool_definitions_is_builtin", "tool_definitions", ["is_builtin"])
    if "builtin_handler" not in columns:
        op.add_column("tool_definitions", sa.Column("builtin_handler", sa.String(length=200), nullable=True))
        op.create_index("ix_tool_definitions_builtin_handler", "tool_definitions", ["builtin_handler"])


def _create_tool_invocations() -> None:
    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tool_id", sa.String(length=36), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("tool_name", sa.String(length=200), nullable=False),
        sa.Column("tool_type", sa.String(length=60), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_definitions.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tool_id", "owner_id", "workspace_id", "conversation_id", "tool_name", "tool_type", "status"):
        op.create_index(f"ix_tool_invocations_{column}", "tool_invocations", [column])


def _create_skill_runs() -> None:
    op.create_table(
        "skill_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("runtime_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("skill_id", "owner_id", "conversation_id", "runtime_type", "status"):
        op.create_index(f"ix_skill_runs_{column}", "skill_runs", [column])
