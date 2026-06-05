"""add external agent runs

Revision ID: 9f1c2d3e4a5b
Revises: 61d7d149ab8f
Create Date: 2026-06-05 09:12:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f1c2d3e4a5b"
down_revision: Union[str, None] = "61d7d149ab8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "external_agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("cwd", sa.Text(), nullable=False),
        sa.Column("input_prompt", sa.Text(), nullable=False),
        sa.Column("stdout_tail", sa.Text(), nullable=False),
        sa.Column("stderr_tail", sa.Text(), nullable=False),
        sa.Column("changed_files", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_external_agent_runs_agent_id"), "external_agent_runs", ["agent_id"])
    op.create_index(op.f("ix_external_agent_runs_conversation_id"), "external_agent_runs", ["conversation_id"])
    op.create_index(op.f("ix_external_agent_runs_owner_id"), "external_agent_runs", ["owner_id"])
    op.create_index(op.f("ix_external_agent_runs_provider"), "external_agent_runs", ["provider"])
    op.create_index(op.f("ix_external_agent_runs_status"), "external_agent_runs", ["status"])
    op.create_index(op.f("ix_external_agent_runs_workspace_id"), "external_agent_runs", ["workspace_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_external_agent_runs_workspace_id"), table_name="external_agent_runs")
    op.drop_index(op.f("ix_external_agent_runs_status"), table_name="external_agent_runs")
    op.drop_index(op.f("ix_external_agent_runs_provider"), table_name="external_agent_runs")
    op.drop_index(op.f("ix_external_agent_runs_owner_id"), table_name="external_agent_runs")
    op.drop_index(op.f("ix_external_agent_runs_conversation_id"), table_name="external_agent_runs")
    op.drop_index(op.f("ix_external_agent_runs_agent_id"), table_name="external_agent_runs")
    op.drop_table("external_agent_runs")
