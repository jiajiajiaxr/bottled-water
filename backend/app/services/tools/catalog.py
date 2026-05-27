from __future__ import annotations

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import ToolDefinition, ToolInvocation, User
from app.services.serialization import tool_definition_to_dict
from app.services.tools.builtins.registry import BUILTIN_TOOLS


def ensure_tool_tables(db: Session) -> None:
    for table in (ToolDefinition.__table__, ToolInvocation.__table__):
        table.create(bind=db.get_bind(), checkfirst=True)
    ensure_tool_definition_columns(db)


def ensure_tool_definition_columns(db: Session) -> None:
    columns = {column["name"] for column in inspect(db.get_bind()).get_columns("tool_definitions")}
    dialect = db.get_bind().dialect.name
    if "is_builtin" not in columns:
        column_type = "BOOLEAN" if dialect != "sqlite" else "INTEGER"
        db.execute(text(f"ALTER TABLE tool_definitions ADD COLUMN is_builtin {column_type} DEFAULT 0"))
    if "builtin_handler" not in columns:
        db.execute(text("ALTER TABLE tool_definitions ADD COLUMN builtin_handler VARCHAR(200)"))


def sync_builtin_tool_definitions(db: Session) -> None:
    ensure_tool_tables(db)
    existing = {
        item.name: item
        for item in db.scalars(
            select(ToolDefinition).where(
                ToolDefinition.owner_id.is_(None),
                ToolDefinition.workspace_id.is_(None),
                ToolDefinition.name.in_(list(BUILTIN_TOOLS)),
            )
        ).all()
    }
    for name, builtin in BUILTIN_TOOLS.items():
        tool = existing.get(name)
        if not tool:
            tool = ToolDefinition(owner_id=None, workspace_id=None, name=name)
            db.add(tool)
        tool.display_name = builtin.display_name
        tool.description = builtin.description
        tool.category = builtin.category
        tool.type = "builtin"
        tool.is_builtin = True
        tool.builtin_handler = name
        tool.status = "active"
        tool.deleted_at = None
        tool.version = "1.0.0"
        tool.input_schema = builtin.input_schema
        tool.output_schema = builtin.output_schema
        tool.permissions = list(builtin.permissions)
        tool.implementation = {"builtin_handler": name}
        tool.runtime = {"mode": "builtin", "executor": "app.services.tools.builtins.executor"}
        tool.tags = list(builtin.tags)
        tool.config = {"builtin": True}
    db.flush()


def visible_tool_query(user: User, workspace_id: str | None = None):
    query = select(ToolDefinition).where(ToolDefinition.deleted_at.is_(None))
    if user.role != "admin":
        query = query.where((ToolDefinition.owner_id == user.id) | (ToolDefinition.owner_id.is_(None)))
    if workspace_id:
        query = query.where((ToolDefinition.workspace_id == workspace_id) | (ToolDefinition.workspace_id.is_(None)))
    return query


def list_tools(
    db: Session,
    user: User,
    *,
    workspace_id: str | None = None,
    q: str | None = None,
) -> list[dict]:
    ensure_tool_tables(db)
    sync_builtin_tool_definitions(db)
    items = [
        tool_definition_to_dict(item)
        for item in db.scalars(visible_tool_query(user, workspace_id)).all()
    ]
    if q:
        needle = q.lower()
        items = [
            item
            for item in items
            if needle in item["name"].lower()
            or needle in item.get("display_name", "").lower()
            or needle in item.get("description", "").lower()
            or needle in item.get("category", "").lower()
        ]
    items.sort(key=lambda item: (item.get("category", ""), item.get("name", "")))
    return items


def get_custom_tool(db: Session, user: User, tool_id_or_name: str) -> ToolDefinition:
    return get_tool_definition(db, user, tool_id_or_name)


def get_tool_definition(db: Session, user: User, tool_id_or_name: str) -> ToolDefinition:
    ensure_tool_tables(db)
    sync_builtin_tool_definitions(db)
    tool = db.scalar(
        visible_tool_query(user).where(
            (ToolDefinition.id == tool_id_or_name) | (ToolDefinition.name == tool_id_or_name)
        )
    )
    if not tool:
        raise NotFoundError("Tool not found")
    return tool
