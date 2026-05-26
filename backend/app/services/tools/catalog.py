from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import ToolDefinition, User
from app.services.serialization import tool_definition_to_dict
from app.services.tools.builtins import builtin_tool_dicts


def ensure_tool_tables(db: Session) -> None:
    ToolDefinition.__table__.create(bind=db.get_bind(), checkfirst=True)


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
    items = builtin_tool_dicts()
    custom = [
        tool_definition_to_dict(item)
        for item in db.scalars(visible_tool_query(user, workspace_id)).all()
    ]
    items.extend(custom)
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
    ensure_tool_tables(db)
    tool = db.scalar(
        visible_tool_query(user).where(
            (ToolDefinition.id == tool_id_or_name) | (ToolDefinition.name == tool_id_or_name)
        )
    )
    if not tool:
        raise NotFoundError("?????")
    return tool
