from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError
from app.core.response import ok
from app.deps import get_current_user
from app.models import RemoteConnection, SandboxSession, User, Workspace, utcnow
from app.schemas.requests import CreateRemoteConnectionRequest, CreateSandboxRequest, RunSandboxCommandRequest
from app.services.serialization import remote_connection_to_dict, sandbox_to_dict
from app.services.tools.builtins.sandbox.executor import run_existing_sandbox_command
from app.services.workspaces.filesystem import list_files, scoped_dir


router = APIRouter(tags=["sandbox-remote"])


def ensure_sandbox_tables(db: Session) -> None:
    for table in (SandboxSession.__table__, RemoteConnection.__table__):
        table.create(bind=db.get_bind(), checkfirst=True)


def _validate_workspace(db: Session, user: User, workspace_id: str | None) -> None:
    if not workspace_id:
        return
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("workspace not found")
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("no permission to access this workspace")


def _get_sandbox(db: Session, user: User, sandbox_id: str) -> SandboxSession:
    ensure_sandbox_tables(db)
    sandbox = db.scalar(
        select(SandboxSession).where(SandboxSession.id == sandbox_id, SandboxSession.deleted_at.is_(None))
    )
    if not sandbox:
        raise NotFoundError("sandbox not found")
    if sandbox.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("no permission to access this sandbox")
    return sandbox


@router.get("/sandboxes")
async def list_sandboxes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_sandbox_tables(db)
    items = db.scalars(
        select(SandboxSession)
        .where(SandboxSession.owner_id == user.id, SandboxSession.deleted_at.is_(None))
        .order_by(SandboxSession.updated_at.desc())
    ).all()
    return ok({"items": [sandbox_to_dict(item) for item in items], "total": len(items)})


@router.post("/sandboxes")
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
        mounted_files=list_files(scoped_dir(payload.workspace_id or "default", "sandbox", task_id=payload.project_id)),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return ok(sandbox_to_dict(session), "sandbox created")


@router.post("/sandboxes/{sandbox_id}/commands")
async def run_sandbox_command(
    sandbox_id: str,
    payload: RunSandboxCommandRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_sandbox(db, user, sandbox_id)
    result = run_existing_sandbox_command(
        db,
        user,
        session,
        command=payload.command.strip(),
        timeout=payload.timeout_seconds,
        workdir=payload.workdir or payload.cwd or "",
    )
    db.commit()
    db.refresh(session)
    return ok({"sandbox": sandbox_to_dict(session), "result": result}, "command completed")


@router.post("/sandboxes/{sandbox_id}/stop")
async def stop_sandbox(
    sandbox_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    session = _get_sandbox(db, user, sandbox_id)
    session.status = "stopped"
    db.commit()
    return ok(sandbox_to_dict(session), "sandbox stopped")


@router.get("/remote-connections")
async def list_remote_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_sandbox_tables(db)
    items = db.scalars(
        select(RemoteConnection)
        .where(RemoteConnection.owner_id == user.id, RemoteConnection.deleted_at.is_(None))
        .order_by(RemoteConnection.updated_at.desc())
    ).all()
    return ok({"items": [remote_connection_to_dict(item) for item in items], "total": len(items)})


@router.post("/remote-connections")
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
    return ok(remote_connection_to_dict(connection), "remote connection created")


@router.post("/remote-connections/{connection_id}/connect")
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
        raise NotFoundError("remote connection not found")
    if connection.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("no permission to access this remote connection")
    connection.status = "connected"
    connection.last_connected_at = utcnow()
    connection.session_state = {"active_tab": connection.endpoint or "about:blank", "mode": connection.connection_type}
    db.commit()
    return ok(remote_connection_to_dict(connection), "remote connection established")
