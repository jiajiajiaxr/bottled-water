from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.models import McpServer, McpToolInvocation, User, Workspace


def ensure_mcp_tables(db: Session) -> None:
    for table in (McpServer.__table__, McpToolInvocation.__table__):
        table.create(bind=db.get_bind(), checkfirst=True)


def validate_workspace(db: Session, user: User, workspace_id: str | None) -> None:
    if not workspace_id:
        return
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("工作区不存在")
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权配置该工作区 MCP")


def visible_server_query(user: User, workspace_id: str | None = None):
    query = select(McpServer).where(McpServer.deleted_at.is_(None))
    if user.role != "admin":
        query = query.where((McpServer.owner_id == user.id) | (McpServer.owner_id.is_(None)))
    if workspace_id:
        query = query.where(McpServer.workspace_id == workspace_id)
    return query


def get_server_for_user(db: Session, user: User, server_id: str) -> McpServer:
    ensure_mcp_tables(db)
    server = db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.deleted_at.is_(None)))
    if not server:
        raise NotFoundError("MCP 服务不存在")
    if server.owner_id not in {None, user.id} and user.role != "admin":
        raise ForbiddenError("无权访问该 MCP 服务")
    return server


def ensure_server_owner(server: McpServer, user: User) -> None:
    if server.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只有创建者可以修改 MCP 服务")
