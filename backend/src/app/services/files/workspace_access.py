from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Artifact, Conversation, FileAsset, Project, ProjectFile, User, Workspace, WorkspaceMember
from app.services.files import encrypted_file_response_content
from app.services.workspaces.filesystem import normalize_relative_path, resolve_workspace_path, workspace_root


def workspace_conversations(db: Session, workspace_id: str) -> list[Conversation]:
    conversations = db.scalars(select(Conversation).where(Conversation.deleted_at.is_(None))).all()
    return [
        item
        for item in conversations
        if isinstance(item.extra, dict)
        and str(item.extra.get("workspace_id") or item.extra.get("workspaceId") or "") == workspace_id
    ]


def assert_workspace_access(db: Session, user: User, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("工作区不存在")
    if user.role == "admin" or workspace.owner_id == user.id:
        return workspace
    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.left_at.is_(None),
        )
    )
    if not member:
        raise ForbiddenError("无权访问该工作区文件")
    return workspace


def file_asset(db: Session, workspace_id: str, file_id: str) -> FileAsset:
    asset = db.get(FileAsset, file_id)
    if not asset or asset.deleted_at is not None:
        raise NotFoundError("文件不存在")
    conversations = {item.id for item in workspace_conversations(db, workspace_id)}
    if not asset_in_workspace(asset, workspace_id, conversations):
        raise ForbiddenError("文件不属于当前工作区")
    return asset


def artifact(db: Session, workspace_id: str, artifact_id: str) -> Artifact:
    item = db.get(Artifact, artifact_id)
    if not item or item.deleted_at is not None:
        raise NotFoundError("产物不存在")
    if item.conversation_id not in {conversation.id for conversation in workspace_conversations(db, workspace_id)}:
        raise ForbiddenError("产物不属于当前工作区")
    return item


def project_file(db: Session, workspace_id: str, file_id: str) -> ProjectFile:
    item = db.get(ProjectFile, file_id)
    if not item:
        raise NotFoundError("项目文件不存在")
    project = db.get(Project, item.project_id)
    if not project or project.workspace_id != workspace_id or project.deleted_at is not None:
        raise ForbiddenError("项目文件不属于当前工作区")
    return item


def file_asset_target(workspace_id: str, asset: FileAsset) -> dict[str, Any]:
    root = workspace_root(workspace_id)
    relative_path = relative_or_compat(root, Path(asset.storage_path), f"uploads/legacy/{asset.original_filename}")
    target = {
        "kind": "file",
        "path": Path(asset.storage_path),
        "filename": asset.original_filename,
        "mime_type": asset.content_type,
        "relative_path": relative_path,
        "file_asset": asset,
    }
    decrypted = encrypted_file_response_content(asset)
    if decrypted is not None:
        target["bytes"] = decrypted
    return target


def safe_workspace_file_path(workspace_id: str, encoded_path: str) -> Path:
    relative_path = normalize_relative_path(unquote(encoded_path))
    path = resolve_workspace_path(workspace_root(workspace_id), relative_path)
    if not path.exists() or not path.is_file():
        raise NotFoundError("文件不存在")
    return path


def safe_workspace_dir_path(workspace_id: str, encoded_path: str, *, create: bool = False) -> Path:
    relative_path = normalize_relative_path(unquote(encoded_path))
    path = resolve_workspace_path(workspace_root(workspace_id), relative_path)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise NotFoundError("文件夹不存在")
    return path


def safe_filename(value: str) -> str:
    cleaned = Path(str(value or "").replace("\\", "/")).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValidationAppError("文件名不合法")
    return cleaned[:180]


def split_node_id(node_id: str) -> tuple[str, str]:
    if ":" not in node_id:
        raise ValidationAppError("node_id 格式不正确")
    kind, value = node_id.split(":", 1)
    if not value:
        raise ValidationAppError("node_id 格式不正确")
    return kind, value


def asset_in_workspace(asset: FileAsset, workspace_id: str, conversation_ids: set[str]) -> bool:
    extra = asset.extra if isinstance(asset.extra, dict) else {}
    return (
        str(extra.get("workspace_id") or "") == workspace_id
        or asset.conversation_id in conversation_ids
        or path_under_workspace(asset.storage_path, workspace_id)
    )


def relative_or_compat(root: Path, path: Path, fallback: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return fallback


def path_under_workspace(storage_path: str, workspace_id: str) -> bool:
    try:
        Path(storage_path).resolve().relative_to(workspace_root(workspace_id).resolve())
        return True
    except ValueError:
        return False
