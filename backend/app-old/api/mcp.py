from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ValidationAppError, NotFoundError
from app.core.response import ok
from app.deps import get_current_user
from app.models import McpServer, McpToolInvocation, User, utcnow
from app.schemas.requests import CreateMcpServerRequest, ImportMcpServerRequest, InvokeMcpToolRequest
from app.services.mcp.catalog import (
    ensure_mcp_tables,
    ensure_server_owner,
    get_server_for_user,
    validate_workspace,
    visible_server_query,
)
from app.services.mcp.discovery import discover_server_tools, import_server_manifest, probe_server
from app.services.mcp.invocation import invoke_mcp_tool_recorded
from app.services.serialization import mcp_invocation_to_dict, mcp_server_to_dict


router = APIRouter(tags=["mcp"])


def _get_server(db: Session, user: User, server_id: str) -> McpServer:
    return get_server_for_user(db, user, server_id)


@router.get("/mcp-servers")
async def list_mcp_servers(
    workspace_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_mcp_tables(db)
    query = visible_server_query(user, workspace_id)
    servers = db.scalars(query.order_by(McpServer.created_at.desc())).all()
    return ok({"items": [mcp_server_to_dict(item) for item in servers], "total": len(servers)})


@router.post("/mcp-servers")
async def create_mcp_server(
    payload: CreateMcpServerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_mcp_tables(db)
    validate_workspace(db, user, payload.workspace_id)
    if payload.transport in {"httpStream", "ws", "sse"} and not payload.url:
        raise ValidationAppError("远程MCP服务必须配置URL")
    if payload.transport == "stdio" and not payload.command:
        raise ValidationAppError("stdio MCP服务必须配置启动命令")
    server = McpServer(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        name=payload.name,
        transport=payload.transport,
        url=payload.url,
        command=payload.command,
        args=payload.args,
        env=payload.env,
        headers=payload.headers,
        enabled=payload.enabled,
        tool_filter=payload.tool_filter,
        timeout_ms=payload.timeout_ms,
        retry=payload.retry,
        health_status="unknown",
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return ok(mcp_server_to_dict(server), "MCP服务已创建")


@router.post("/mcp-servers/import")
async def import_mcp_server(
    payload: ImportMcpServerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_mcp_tables(db)
    validate_workspace(db, user, payload.workspace_id)
    manifest = import_server_manifest(payload.source_type, payload.source)
    transport = manifest.get("transport") or manifest.get("type") or "stdio"
    server = McpServer(
        owner_id=user.id,
        workspace_id=payload.workspace_id or manifest.get("workspace_id"),
        name=manifest.get("name") or manifest.get("server_name") or "Imported MCP",
        transport=transport,
        url=manifest.get("url") or manifest.get("endpoint"),
        command=manifest.get("command"),
        args=manifest.get("args") if isinstance(manifest.get("args"), list) else [],
        env=manifest.get("env") if isinstance(manifest.get("env"), dict) else {},
        headers=manifest.get("headers") if isinstance(manifest.get("headers"), dict) else {},
        enabled=bool(manifest.get("enabled", True)),
        tool_filter=manifest.get("tool_filter") if isinstance(manifest.get("tool_filter"), list) else [],
        timeout_ms=int(manifest.get("timeout_ms") or 30000),
        retry=int(manifest.get("retry") or 1),
        health_status="unknown",
        tools=manifest.get("tools") if isinstance(manifest.get("tools"), list) else [],
        extra={"import_source_type": payload.source_type},
    )
    if server.transport in {"httpStream", "ws", "sse"} and not server.url:
        raise ValidationAppError("远程 MCP 配置必须包含 url")
    if server.transport == "stdio" and not server.command:
        raise ValidationAppError("stdio MCP 配置必须包含 command")
    db.add(server)
    db.commit()
    db.refresh(server)
    return ok(mcp_server_to_dict(server), "MCP 已导入")


@router.patch("/mcp-servers/{server_id}")
async def update_mcp_server(
    server_id: str,
    payload: CreateMcpServerRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _get_server(db, user, server_id)
    ensure_server_owner(server, user)
    validate_workspace(db, user, payload.workspace_id)
    server.workspace_id = payload.workspace_id
    server.name = payload.name
    server.transport = payload.transport
    server.url = payload.url
    server.command = payload.command
    server.args = payload.args
    server.env = payload.env
    server.headers = payload.headers
    server.enabled = payload.enabled
    server.tool_filter = payload.tool_filter
    server.timeout_ms = payload.timeout_ms
    server.retry = payload.retry
    db.commit()
    return ok(mcp_server_to_dict(server), "MCP服务已更新")


@router.post("/mcp-servers/{server_id}/probe")
async def probe_mcp_server(
    server_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _get_server(db, user, server_id)
    probe_server(server)
    db.commit()
    return ok(mcp_server_to_dict(server), "MCP服务探测完成")


@router.get("/mcp-servers/{server_id}/tools")
async def list_mcp_tools(
    server_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _get_server(db, user, server_id)
    tools = discover_server_tools(server)
    return ok({"server_id": server.id, "items": tools, "total": len(tools)})


@router.post("/mcp-servers/{server_id}/tools/{tool_name:path}/invoke")
async def invoke_mcp_tool(
    server_id: str,
    tool_name: str,
    payload: InvokeMcpToolRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _get_server(db, user, server_id)
    invocation = await invoke_mcp_tool_recorded(
        db,
        server=server,
        tool_name_value=tool_name,
        arguments=payload.arguments,
        user=user,
        conversation_id=payload.conversation_id,
        timeout_ms=payload.timeout_ms or server.timeout_ms or 30000,
    )
    db.commit()
    return ok(invocation, "MCP tool invocation recorded")


@router.get("/mcp-invocations")
async def list_mcp_invocations(
    server_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_mcp_tables(db)
    query = select(McpToolInvocation).where(McpToolInvocation.owner_id == user.id)
    if user.role in {"admin", "developer"}:
        query = select(McpToolInvocation)
    if server_id:
        query = query.where(McpToolInvocation.server_id == server_id)
    if status:
        query = query.where(McpToolInvocation.status == status)
    items = db.scalars(query.order_by(McpToolInvocation.created_at.desc()).limit(100)).all()
    return ok({"items": [mcp_invocation_to_dict(item) for item in items], "total": len(items)})


@router.get("/mcp-invocations/{invocation_id}")
async def get_mcp_invocation(
    invocation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_mcp_tables(db)
    invocation = db.get(McpToolInvocation, invocation_id)
    if not invocation or (invocation.owner_id != user.id and user.role not in {"admin", "developer"}):
        raise NotFoundError("MCP invocation not found")
    return ok(mcp_invocation_to_dict(invocation))


@router.delete("/mcp-servers/{server_id}")
async def delete_mcp_server(
    server_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    server = _get_server(db, user, server_id)
    ensure_server_owner(server, user)
    server.deleted_at = utcnow()
    server.enabled = False
    db.commit()
    return ok({"id": server.id, "deleted": True})
