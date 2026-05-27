from __future__ import annotations

import shlex

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import RemoteConnection, SandboxSession, User, Workspace, utcnow
from app.schemas.common import ApiResponse, RemoteConnectionOut, SandboxOut
from app.schemas.requests import CreateRemoteConnectionRequest, CreateSandboxRequest, RunSandboxCommandRequest
from app.services.serialization import remote_connection_to_dict, sandbox_to_dict


router = APIRouter(tags=["sandbox-remote"])


def ensure_sandbox_tables(db: Session) -> None:
    for table in (SandboxSession.__table__, RemoteConnection.__table__):
        table.create(bind=db.get_bind(), checkfirst=True)


def _validate_workspace(db: Session, user: User, workspace_id: str | None) -> None:
    if not workspace_id:
        return
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("工作区不存在")
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该工作区")


def _get_sandbox(db: Session, user: User, sandbox_id: str) -> SandboxSession:
    ensure_sandbox_tables(db)
    sandbox = db.scalar(select(SandboxSession).where(SandboxSession.id == sandbox_id, SandboxSession.deleted_at.is_(None)))
    if not sandbox:
        raise NotFoundError("沙箱不存在")
    if sandbox.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该沙箱")
    return sandbox


@router.get("/sandboxes", response_model=ApiResponse[dict])
async def list_sandboxes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_sandbox_tables(db)
    items = db.scalars(
        select(SandboxSession)
        .where(SandboxSession.owner_id == user.id, SandboxSession.deleted_at.is_(None))
        .order_by(SandboxSession.updated_at.desc())
    ).all()
    return ok({"items": [sandbox_to_dict(item) for item in items], "total": len(items)})


@router.post("/sandboxes", response_model=ApiResponse[SandboxOut])
async def create_sandbox(
    payload: CreateSandboxRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_sandbox_tables(db)
    _validate_workspace(db, user, payload.workspace_id)
    session = SandboxSession(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        project_id=payload.project_id,
        name=payload.name,
        image=payload.image,
        status="ready",
        resource_limits=payload.resource_limits or {"cpu": "1", "memory": "1Gi", "timeout_seconds": 300},
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return ok(sandbox_to_dict(session), "沙箱已创建")


@router.post("/sandboxes/{sandbox_id}/commands", response_model=ApiResponse[dict])
async def run_sandbox_command(
    sandbox_id: str,
    payload: RunSandboxCommandRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_sandbox(db, user, sandbox_id)
    command = payload.command.strip()
    if not command:
        raise ValidationAppError("命令不能为空")
    blocked = {"rm -rf /", "format", "shutdown", "reboot"}
    if any(item in command.lower() for item in blocked):
        raise ValidationAppError("命令被沙箱安全策略拦截")
    session.status = "running"
    session.last_command_at = utcnow()
    output = {
        "command": command,
        "argv": shlex.split(command, posix=False),
        "exit_code": 0,
        "stdout": f"[mock-sandbox] 已在 {session.image} 中执行：{command}",
        "stderr": "",
        "duration_ms": min(payload.timeout_seconds * 1000, 1200),
        "created_at": utcnow().isoformat(),
    }
    session.command_history = [output, *(session.command_history or [])][:50]
    session.status = "ready"
    db.commit()
    return ok({"sandbox": sandbox_to_dict(session), "result": output}, "命令执行完成")


@router.post("/sandboxes/{sandbox_id}/stop", response_model=ApiResponse[SandboxOut])
async def stop_sandbox(
    sandbox_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_sandbox(db, user, sandbox_id)
    session.status = "stopped"
    db.commit()
    return ok(sandbox_to_dict(session), "沙箱已停止")


@router.get("/remote-connections", response_model=ApiResponse[dict])
async def list_remote_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_sandbox_tables(db)
    items = db.scalars(
        select(RemoteConnection)
        .where(RemoteConnection.owner_id == user.id, RemoteConnection.deleted_at.is_(None))
        .order_by(RemoteConnection.updated_at.desc())
    ).all()
    return ok({"items": [remote_connection_to_dict(item) for item in items], "total": len(items)})


@router.post("/remote-connections", response_model=ApiResponse[RemoteConnectionOut])
async def create_remote_connection(
    payload: CreateRemoteConnectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_sandbox_tables(db)
    _validate_workspace(db, user, payload.workspace_id)
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
    db.commit()
    db.refresh(connection)
    return ok(remote_connection_to_dict(connection), "远程连接已创建")


@router.post("/remote-connections/{connection_id}/connect", response_model=ApiResponse[RemoteConnectionOut])
async def connect_remote(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_sandbox_tables(db)
    connection = db.scalar(
        select(RemoteConnection).where(RemoteConnection.id == connection_id, RemoteConnection.deleted_at.is_(None))
    )
    if not connection:
        raise NotFoundError("远程连接不存在")
    if connection.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问远程连接")
    connection.status = "connected"
    connection.last_connected_at = utcnow()
    connection.session_state = {"active_tab": connection.endpoint or "about:blank", "mode": connection.connection_type}
    db.commit()
    return ok(remote_connection_to_dict(connection), "远程连接已建立")
