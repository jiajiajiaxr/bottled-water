from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Artifact, Conversation, FileAsset, Project, ProjectFile, User, Workspace, WorkspaceMember, utcnow
from app.services.files.workspace_naming import guess_mime
from app.services.files.workspace_nodes import collect_workspace_file_root
from app.services.tools.builtins.artifact.export import export_artifact
from app.services.workspaces.filesystem import normalize_relative_path, resolve_workspace_path, workspace_root


def workspace_file_tree(db: Session, user: User, workspace_id: str) -> dict[str, Any]:
    _assert_workspace_access(db, user, workspace_id)
    conversations = _workspace_conversations(db, workspace_id)
    tree = collect_workspace_file_root(
        db,
        user=user,
        workspace_id=workspace_id,
        root=workspace_root(workspace_id),
        conversations=conversations,
    )
    return {"workspace_id": workspace_id, "root": tree.to_dict(), "items": [item.to_dict() for item in tree.children]}


def get_workspace_file_target(db: Session, user: User, workspace_id: str, node_id: str) -> dict[str, Any]:
    _assert_workspace_access(db, user, workspace_id)
    kind, value = _split_node_id(node_id)
    if kind == "file":
        asset = _file_asset(db, workspace_id, value)
        return _file_asset_target(workspace_id, asset)
    if kind == "artifact":
        exported = export_artifact(_artifact(db, workspace_id, value))
        return {"kind": kind, "bytes": exported.content, "filename": exported.filename, "mime_type": exported.media_type}
    if kind == "project":
        project_file = _project_file(db, workspace_id, value)
        return {
            "kind": kind,
            "text": project_file.content,
            "filename": Path(project_file.path).name,
            "mime_type": guess_mime(project_file.path),
            "relative_path": f"projects/{project_file.path}",
        }
    if kind == "fs":
        path = _safe_workspace_file_path(workspace_id, value)
        return {"kind": kind, "path": path, "filename": path.name, "mime_type": guess_mime(path.name), "relative_path": unquote(value)}
    raise NotFoundError("文件不存在")


def delete_workspace_file_node(db: Session, user: User, workspace_id: str, node_id: str) -> dict[str, Any]:
    _assert_workspace_access(db, user, workspace_id)
    kind, value = _split_node_id(node_id)
    if kind == "file":
        _file_asset(db, workspace_id, value).deleted_at = utcnow()
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "artifact":
        _artifact(db, workspace_id, value).deleted_at = utcnow()
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "project":
        db.delete(_project_file(db, workspace_id, value))
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "fs":
        _safe_workspace_file_path(workspace_id, value).unlink(missing_ok=True)
        return {"id": node_id, "deleted": True}
    raise NotFoundError("文件不存在")


def rename_workspace_file_node(db: Session, user: User, workspace_id: str, node_id: str, new_name: str) -> dict[str, Any]:
    _assert_workspace_access(db, user, workspace_id)
    cleaned = _safe_filename(new_name)
    kind, value = _split_node_id(node_id)
    if kind == "file":
        asset = _file_asset(db, workspace_id, value)
        asset.original_filename = cleaned
        asset.filename = cleaned
        db.commit()
        return _rename_result(node_id, cleaned)
    if kind == "artifact":
        artifact = _artifact(db, workspace_id, value)
        content = dict(artifact.content or {})
        content["filename"] = cleaned
        artifact.name = Path(cleaned).stem
        artifact.content = content
        db.commit()
        return _rename_result(node_id, cleaned)
    if kind == "project":
        project_file = _project_file(db, workspace_id, value)
        project_file.path = normalize_relative_path(str(Path(project_file.path).with_name(cleaned)))
        db.commit()
        return _rename_result(node_id, cleaned)
    if kind == "fs":
        path = _safe_workspace_file_path(workspace_id, value)
        target = resolve_workspace_path(path.parent, cleaned)
        if target.exists():
            raise ValidationAppError("同名文件已存在")
        path.rename(target)
        return _rename_result(node_id, cleaned)
    raise NotFoundError("文件不存在")


def _workspace_conversations(db: Session, workspace_id: str) -> list[Conversation]:
    conversations = db.scalars(select(Conversation).where(Conversation.deleted_at.is_(None))).all()
    return [
        item
        for item in conversations
        if isinstance(item.extra, dict)
        and str(item.extra.get("workspace_id") or item.extra.get("workspaceId") or "") == workspace_id
    ]


def _assert_workspace_access(db: Session, user: User, workspace_id: str) -> Workspace:
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


def _file_asset(db: Session, workspace_id: str, file_id: str) -> FileAsset:
    asset = db.get(FileAsset, file_id)
    if not asset or asset.deleted_at is not None:
        raise NotFoundError("文件不存在")
    conversations = {item.id for item in _workspace_conversations(db, workspace_id)}
    if not _asset_in_workspace(asset, workspace_id, conversations):
        raise ForbiddenError("文件不属于当前工作区")
    return asset


def _artifact(db: Session, workspace_id: str, artifact_id: str) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if not artifact or artifact.deleted_at is not None:
        raise NotFoundError("产物不存在")
    if artifact.conversation_id not in {item.id for item in _workspace_conversations(db, workspace_id)}:
        raise ForbiddenError("产物不属于当前工作区")
    return artifact


def _project_file(db: Session, workspace_id: str, file_id: str) -> ProjectFile:
    item = db.get(ProjectFile, file_id)
    if not item:
        raise NotFoundError("项目文件不存在")
    project = db.get(Project, item.project_id)
    if not project or project.workspace_id != workspace_id or project.deleted_at is not None:
        raise ForbiddenError("项目文件不属于当前工作区")
    return item


def _asset_in_workspace(asset: FileAsset, workspace_id: str, conversation_ids: set[str]) -> bool:
    extra = asset.extra if isinstance(asset.extra, dict) else {}
    return (
        str(extra.get("workspace_id") or "") == workspace_id
        or asset.conversation_id in conversation_ids
        or _path_under_workspace(asset.storage_path, workspace_id)
    )


def _file_asset_target(workspace_id: str, asset: FileAsset) -> dict[str, Any]:
    root = workspace_root(workspace_id)
    relative_path = _relative_or_compat(root, Path(asset.storage_path), f"uploads/legacy/{asset.original_filename}")
    return {
        "kind": "file",
        "path": Path(asset.storage_path),
        "filename": asset.original_filename,
        "mime_type": asset.content_type,
        "relative_path": relative_path,
        "file_asset": asset,
    }


def _safe_workspace_file_path(workspace_id: str, encoded_path: str) -> Path:
    relative_path = normalize_relative_path(unquote(encoded_path))
    path = resolve_workspace_path(workspace_root(workspace_id), relative_path)
    if not path.exists() or not path.is_file():
        raise NotFoundError("文件不存在")
    return path


def _safe_filename(value: str) -> str:
    cleaned = Path(str(value or "").replace("\\", "/")).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise ValidationAppError("文件名不合法")
    return cleaned[:180]


def _split_node_id(node_id: str) -> tuple[str, str]:
    if ":" not in node_id:
        raise ValidationAppError("node_id 格式不正确")
    kind, value = node_id.split(":", 1)
    if not value:
        raise ValidationAppError("node_id 格式不正确")
    return kind, value


def _rename_result(node_id: str, name: str) -> dict[str, str]:
    return {"id": node_id, "name": name, "display_name": name}


def _relative_or_compat(root: Path, path: Path, fallback: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return fallback


def _path_under_workspace(storage_path: str, workspace_id: str) -> bool:
    try:
        Path(storage_path).resolve().relative_to(workspace_root(workspace_id).resolve())
        return True
    except ValueError:
        return False
