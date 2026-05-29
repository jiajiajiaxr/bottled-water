from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Conversation, FileAsset, Project, ProjectFile, User
from app.services.files.workspace_naming import display_name, guess_mime, should_hide_file, source_from_path
from app.services.files.workspace_node_types import WorkspaceFileNode
from app.services.workspaces.filesystem import normalize_relative_path


def upload_nodes(
    db: Session,
    user: User,
    workspace_id: str,
    root: Path,
    conversations: list[Conversation],
) -> list[WorkspaceFileNode]:
    conversation_ids = {item.id for item in conversations}
    assets = db.scalars(select(FileAsset).where(FileAsset.deleted_at.is_(None))).all()
    nodes: list[WorkspaceFileNode] = []
    for asset in assets:
        if _skip_asset(asset, user, workspace_id, conversation_ids):
            continue
        fallback = f"uploads/legacy/{asset.original_filename or asset.filename}"
        display_path = _relative_or_compat(root, Path(asset.storage_path), fallback)
        if should_hide_file(asset.original_filename or asset.filename, asset.size):
            continue
        nodes.append(
            _file_node(
                id=f"file:{asset.id}",
                name=asset.original_filename or asset.filename,
                display_name=display_name(asset.original_filename or asset.filename, fallback_id=asset.id),
                path=display_path,
                source=source_from_path(display_path, asset.purpose or "upload"),
                size=asset.size,
                updated_at=asset.updated_at.isoformat() if asset.updated_at else None,
                mime_type=asset.content_type,
                download_url=f"/api/v1/workspaces/{workspace_id}/files/download?node_id=file:{asset.id}",
                preview_url=f"/api/v1/workspaces/{workspace_id}/files/preview?node_id=file:{asset.id}",
            )
        )
    return nodes


def artifact_nodes(db: Session, workspace_id: str, conversations: list[Conversation]) -> list[WorkspaceFileNode]:
    conversation_ids = {item.id for item in conversations}
    artifacts = db.scalars(
        select(Artifact).where(Artifact.conversation_id.in_(conversation_ids), Artifact.deleted_at.is_(None))
    ).all()
    nodes: list[WorkspaceFileNode] = []
    for artifact in artifacts:
        content = artifact.content or {}
        fmt = content.get("format") or (content.get("tool_output") or {}).get("format") or "html"
        filename = content.get("filename") or f"{artifact.name}.{fmt}"
        folder = str(content.get("workspace_folder") or "").strip("/")
        artifact_path = f"{folder}/{filename}" if folder else f"artifacts/{artifact.id}/{filename}"
        nodes.append(
            _file_node(
                id=f"artifact:{artifact.id}",
                name=filename,
                display_name=display_name(filename, fallback_name=artifact.name, fallback_id=artifact.id),
                path=artifact_path,
                source="artifact",
                size=_artifact_size(artifact),
                updated_at=artifact.updated_at.isoformat() if artifact.updated_at else None,
                mime_type=content.get("media_type") or artifact.mime_type,
                download_url=f"/api/v1/artifacts/{artifact.id}/export?format={fmt}",
                preview_url=f"/api/v1/artifacts/{artifact.id}/preview",
            )
        )
    return nodes


def project_nodes(db: Session, workspace_id: str) -> list[WorkspaceFileNode]:
    projects = db.scalars(select(Project).where(Project.workspace_id == workspace_id, Project.deleted_at.is_(None))).all()
    nodes: list[WorkspaceFileNode] = []
    for project in projects:
        files = db.scalars(select(ProjectFile).where(ProjectFile.project_id == project.id)).all()
        for item in files:
            path = normalize_relative_path(item.path)
            nodes.append(
                _file_node(
                    id=f"project:{item.id}",
                    name=Path(path).name,
                    display_name=display_name(Path(path).name, fallback_id=item.id),
                    path=f"projects/{project.name}/{path}",
                    source="project",
                    size=item.size,
                    updated_at=item.updated_at.isoformat() if item.updated_at else None,
                    mime_type=guess_mime(path),
                    download_url=f"/api/v1/workspaces/{workspace_id}/files/download?node_id=project:{item.id}",
                    preview_url=f"/api/v1/workspaces/{workspace_id}/files/preview?node_id=project:{item.id}",
                )
            )
    return nodes


def filesystem_nodes(workspace_id: str, root: Path, seen_paths: set[str]) -> list[WorkspaceFileNode]:
    nodes: list[WorkspaceFileNode] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        if relative_path.startswith("artifacts/") or relative_path in seen_paths:
            continue
        stat = path.stat()
        if should_hide_file(path.name, stat.st_size):
            continue
        encoded = quote(relative_path, safe="")
        nodes.append(
            _file_node(
                id=f"fs:{encoded}",
                name=path.name,
                display_name=display_name(path.name, fallback_id=relative_path),
                path=relative_path,
                source=source_from_path(relative_path, "workspace"),
                size=stat.st_size,
                updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                mime_type=guess_mime(path.name),
                download_url=f"/api/v1/workspaces/{workspace_id}/files/download?node_id=fs:{encoded}",
                preview_url=f"/api/v1/workspaces/{workspace_id}/files/preview?node_id=fs:{encoded}",
            )
        )
    return nodes


def _file_node(**kwargs: Any) -> WorkspaceFileNode:
    return WorkspaceFileNode(type="file", children=[], **kwargs)


def _skip_asset(asset: FileAsset, user: User, workspace_id: str, conversation_ids: set[str]) -> bool:
    if asset.artifact_id or str(asset.purpose or "").startswith("artifact_"):
        return True
    if user.role != "admin" and asset.owner_id != user.id and asset.conversation_id not in conversation_ids:
        return True
    extra = asset.extra if isinstance(asset.extra, dict) else {}
    return not (
        str(extra.get("workspace_id") or "") == workspace_id
        or asset.conversation_id in conversation_ids
        or _path_under_workspace(asset.storage_path, workspace_id)
    )


def _artifact_size(artifact: Artifact) -> int:
    if artifact.file_size:
        return artifact.file_size
    content = artifact.content or {}
    for key in ("export_file", "source_file"):
        candidate = content.get(key)
        if candidate and Path(str(candidate)).is_file():
            return Path(str(candidate)).stat().st_size
    return 0


def _relative_or_compat(root: Path, path: Path, fallback: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return fallback


def _path_under_workspace(storage_path: str, workspace_id: str) -> bool:
    from app.services.workspaces.filesystem import workspace_root

    try:
        Path(storage_path).resolve().relative_to(workspace_root(workspace_id).resolve())
        return True
    except ValueError:
        return False
