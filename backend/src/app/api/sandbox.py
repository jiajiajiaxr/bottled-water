from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import RemoteConnection, SandboxSession, User, Workspace, utcnow
from app.schemas.common import ApiResponse, RemoteConnectionOut, SandboxOut
from app.schemas.requests import (
    CreateRemoteConnectionRequest,
    CreateSandboxRequest,
    RunSandboxCommandRequest,
    TerminalSendRequest,
    TerminalStartRequest,
    TerminalWaitRequest,
)
from app.services.serialization import remote_connection_to_dict, sandbox_to_dict
from app.services.tools.builtins.sandbox.executor import run_existing_sandbox_command
from app.services.tools.executor import invoke_tool


router = APIRouter(tags=["sandbox-remote"])


async def ensure_sandbox_tables(db: AsyncSession) -> None:
    for table in (SandboxSession.__table__, RemoteConnection.__table__):
        await db.run_sync(lambda session: table.create(bind=session.get_bind(), checkfirst=True))


async def _validate_workspace(db: AsyncSession, user: User, workspace_id: str | None) -> None:
    if not workspace_id:
        return
    workspace = await db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("工作区不存在")
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该工作区")


async def _get_sandbox(db: AsyncSession, user: User, sandbox_id: str) -> SandboxSession:
    await ensure_sandbox_tables(db)
    sandbox = await db.scalar(
        select(SandboxSession).where(
            SandboxSession.id == sandbox_id, SandboxSession.deleted_at.is_(None)
        )
    )
    if not sandbox:
        raise NotFoundError("沙箱不存在")
    if sandbox.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该沙箱")
    return sandbox


@router.get("/sandboxes", response_model=ApiResponse[dict])
async def list_sandboxes(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await ensure_sandbox_tables(db)
    items = (
        await db.scalars(
            select(SandboxSession)
            .where(SandboxSession.owner_id == user.id, SandboxSession.deleted_at.is_(None))
            .order_by(SandboxSession.updated_at.desc())
        )
    ).all()
    return ok({"items": [sandbox_to_dict(item) for item in items], "total": len(items)})


@router.post("/sandboxes", response_model=ApiResponse[SandboxOut])
async def create_sandbox(
    payload: CreateSandboxRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_sandbox_tables(db)
    await _validate_workspace(db, user, payload.workspace_id)
    session = SandboxSession(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        project_id=payload.project_id,
        name=payload.name,
        image=payload.image,
        status="ready",
        resource_limits=payload.resource_limits
        or {"cpu": "1", "memory": "1Gi", "timeout_seconds": 300},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ok(sandbox_to_dict(session), "沙箱已创建")


@router.post("/sandboxes/{sandbox_id}/commands", response_model=ApiResponse[dict])
async def run_sandbox_command(
    sandbox_id: str,
    payload: RunSandboxCommandRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _get_sandbox(db, user, sandbox_id)
    command = payload.command.strip()
    if not command:
        raise ValidationAppError("命令不能为空")
    blocked = {"rm -rf /", "format", "shutdown", "reboot"}
    if any(item in command.lower() for item in blocked):
        raise ValidationAppError("命令被沙箱安全策略拦截")
    output = await db.run_sync(
        lambda sync_db: run_existing_sandbox_command(
            sync_db,
            user,
            session,
            command=command,
            timeout=payload.timeout_seconds,
            workdir=payload.workdir,
        )
    )
    await db.commit()
    await db.refresh(session)
    return ok({"sandbox": sandbox_to_dict(session), "result": output}, "命令执行完成")


@router.post("/terminals", response_model=ApiResponse[dict])
async def start_terminal(
    payload: TerminalStartRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_sandbox_tables(db)
    if payload.workspace_id:
        await _validate_workspace(db, user, payload.workspace_id)
    result = await db.run_sync(
        lambda session: invoke_tool(
            session,
            user,
            "terminal.start",
            payload.model_dump(exclude_none=True),
        )
    )
    await db.commit()
    return ok(result["result"], "terminal started")


@router.post("/terminals/{session_id}/input", response_model=ApiResponse[dict])
async def send_terminal_input(
    session_id: str,
    payload: TerminalSendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.run_sync(
        lambda session: invoke_tool(
            session,
            user,
            "terminal.send",
            {"session_id": session_id, "input": payload.input},
        )
    )
    await db.commit()
    return ok(result["result"], "terminal input sent")


@router.post("/terminals/{session_id}/wait", response_model=ApiResponse[dict])
async def wait_terminal_output(
    session_id: str,
    payload: TerminalWaitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.run_sync(
        lambda session: invoke_tool(
            session,
            user,
            "terminal.wait_for",
            {
                "session_id": session_id,
                "patterns": payload.patterns,
                "timeout_ms": payload.timeout_ms,
            },
        )
    )
    await db.commit()
    return ok(result["result"], "terminal wait completed")


@router.get("/terminals/{session_id}", response_model=ApiResponse[dict])
async def terminal_snapshot(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.run_sync(
        lambda session: invoke_tool(
            session,
            user,
            "terminal.snapshot",
            {"session_id": session_id},
        )
    )
    await db.commit()
    return ok(result["result"], "terminal snapshot")


@router.post("/terminals/{session_id}/stop", response_model=ApiResponse[dict])
async def stop_terminal_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.run_sync(
        lambda session: invoke_tool(
            session,
            user,
            "terminal.stop",
            {"session_id": session_id},
        )
    )
    await db.commit()
    return ok(result["result"], "terminal stopped")


@router.post("/sandboxes/{sandbox_id}/stop", response_model=ApiResponse[SandboxOut])
async def stop_sandbox(
    sandbox_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = await _get_sandbox(db, user, sandbox_id)
    session.status = "stopped"
    await db.commit()
    return ok(sandbox_to_dict(session), "沙箱已停止")


@router.get("/remote-connections", response_model=ApiResponse[dict])
async def list_remote_connections(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await ensure_sandbox_tables(db)
    items = (
        await db.scalars(
            select(RemoteConnection)
            .where(RemoteConnection.owner_id == user.id, RemoteConnection.deleted_at.is_(None))
            .order_by(RemoteConnection.updated_at.desc())
        )
    ).all()
    return ok({"items": [remote_connection_to_dict(item) for item in items], "total": len(items)})


@router.post("/remote-connections", response_model=ApiResponse[RemoteConnectionOut])
async def create_remote_connection(
    payload: CreateRemoteConnectionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_sandbox_tables(db)
    await _validate_workspace(db, user, payload.workspace_id)
    connection = RemoteConnection(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        name=payload.name,
        connection_type=payload.connection_type,
        endpoint=payload.endpoint,
        capabilities=payload.capabilities,
        status="disconnected",
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return ok(remote_connection_to_dict(connection), "远程连接已创建")


@router.post(
    "/remote-connections/{connection_id}/connect", response_model=ApiResponse[RemoteConnectionOut]
)
async def connect_remote(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_sandbox_tables(db)
    connection = await db.scalar(
        select(RemoteConnection).where(
            RemoteConnection.id == connection_id, RemoteConnection.deleted_at.is_(None)
        )
    )
    if not connection:
        raise NotFoundError("远程连接不存在")
    if connection.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问远程连接")
    connection.status = "connected"
    connection.last_connected_at = utcnow()
    connection.session_state = {
        "active_tab": connection.endpoint or "about:blank",
        "mode": connection.connection_type,
    }
    await db.commit()
    return ok(remote_connection_to_dict(connection), "远程连接已建立")
