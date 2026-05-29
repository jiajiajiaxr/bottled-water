from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Artifact, Conversation, FileAsset, Project, ProjectFile, User, Workspace, WorkspaceMember, utcnow
from app.services.tools.builtins.artifact.export import export_artifact
from app.services.workspaces.filesystem import normalize_relative_path, resolve_workspace_path, workspace_root


ROOT_LABELS = {
    "uploads": "上传文件",
    "artifacts": "产物文件",
    "sandbox": "沙箱文件",
    "exports": "导出文件",
    "projects": "项目文件",
    "files": "兼容文件",
}


@dataclass
class WorkspaceFileNode:
    id: str
    name: str
    type: str
    path: str
    source: str
    size: int = 0
    updated_at: str | None = None
    mime_type: str | None = None
    download_url: str | None = None
    preview_url: str | None = None
    children: list["WorkspaceFileNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "path": self.path,
            "size": self.size,
            "updated_at": self.updated_at,
            "source": self.source,
            "mime_type": self.mime_type,
            "download_url": self.download_url,
            "preview_url": self.preview_url,
            "children": [child.to_dict() for child in self.children],
        }


def workspace_file_tree(db: Session, user: User, workspace_id: str) -> dict[str, Any]:
    _assert_workspace_access(db, user, workspace_id)
    root = workspace_root(workspace_id)
    builder = _TreeBuilder(workspace_id)
    seen_paths: set[str] = set()
    for node in _upload_nodes(db, user, workspace_id, root):
        builder.add(node)
        seen_paths.add(node.path)
    for node in _artifact_nodes(db, workspace_id):
        builder.add(node)
    for node in _project_nodes(db, workspace_id):
        builder.add(node)
    for node in _filesystem_nodes(workspace_id, root, seen_paths):
        builder.add(node)
    tree = builder.root()
    return {"workspace_id": workspace_id, "root": tree.to_dict(), "items": [item.to_dict() for item in tree.children]}


def get_workspace_file_target(db: Session, user: User, workspace_id: str, node_id: str) -> dict[str, Any]:
    _assert_workspace_access(db, user, workspace_id)
    kind, value = _split_node_id(node_id)
    if kind == "file":
        asset = _file_asset(db, workspace_id, value)
        return {"kind": kind, "path": Path(asset.storage_path), "filename": asset.original_filename, "mime_type": asset.content_type}
    if kind == "artifact":
        artifact = _artifact(db, workspace_id, value)
        exported = export_artifact(artifact)
        return {"kind": kind, "bytes": exported.content, "filename": exported.filename, "mime_type": exported.media_type}
    if kind == "project":
        project_file = _project_file(db, workspace_id, value)
        return {
            "kind": kind,
            "text": project_file.content,
            "filename": Path(project_file.path).name,
            "mime_type": _guess_mime(project_file.path),
        }
    if kind == "fs":
        path = _safe_workspace_file_path(workspace_id, value)
        return {"kind": kind, "path": path, "filename": path.name, "mime_type": _guess_mime(path.name)}
    raise NotFoundError("文件不存在")


def delete_workspace_file_node(db: Session, user: User, workspace_id: str, node_id: str) -> dict[str, Any]:
    _assert_workspace_access(db, user, workspace_id)
    kind, value = _split_node_id(node_id)
    if kind == "file":
        asset = _file_asset(db, workspace_id, value)
        asset.deleted_at = utcnow()
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "artifact":
        artifact = _artifact(db, workspace_id, value)
        artifact.deleted_at = utcnow()
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "project":
        project_file = _project_file(db, workspace_id, value)
        db.delete(project_file)
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "fs":
        path = _safe_workspace_file_path(workspace_id, value)
        if path.is_file():
            path.unlink()
        return {"id": node_id, "deleted": True}
    raise NotFoundError("文件不存在")


class _TreeBuilder:
    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self.nodes: dict[str, WorkspaceFileNode] = {
            "": WorkspaceFileNode(
                id=f"workspace:{workspace_id}",
                name="工作区文件",
                type="directory",
                path="",
                source="workspace",
            )
        }

    def add(self, node: WorkspaceFileNode) -> None:
        parts = [part for part in node.path.split("/") if part]
        parent_path = ""
        for index, part in enumerate(parts[:-1]):
            current_path = "/".join(parts[: index + 1])
            if current_path not in self.nodes:
                self.nodes[current_path] = WorkspaceFileNode(
                    id=f"dir:{quote(current_path, safe='')}",
                    name=ROOT_LABELS.get(part, part),
                    type="directory",
                    path=current_path,
                    source=parts[0],
                )
                self.nodes[parent_path].children.append(self.nodes[current_path])
            parent_path = current_path
        self.nodes[parent_path].children.append(node)

    def root(self) -> WorkspaceFileNode:
        self._sort(self.nodes[""])
        return self.nodes[""]

    def _sort(self, node: WorkspaceFileNode) -> None:
        node.children.sort(key=lambda item: (item.type != "directory", item.name.lower()))
        for child in node.children:
            self._sort(child)


def _upload_nodes(db: Session, user: User, workspace_id: str, root: Path) -> list[WorkspaceFileNode]:
    conversations = _workspace_conversations(db, workspace_id)
    conversation_ids = {item.id for item in conversations}
    assets = db.scalars(select(FileAsset).where(FileAsset.deleted_at.is_(None))).all()
    nodes: list[WorkspaceFileNode] = []
    for asset in assets:
        if asset.artifact_id or str(asset.purpose or "").startswith("artifact_"):
            continue
        if user.role != "admin" and asset.owner_id != user.id and asset.conversation_id not in conversation_ids:
            continue
        if not _asset_in_workspace(asset, workspace_id, conversation_ids):
            continue
        display_path = _relative_or_compat(root, Path(asset.storage_path), f"uploads/legacy/{asset.id}/{asset.original_filename}")
        nodes.append(
            _file_node(
                id=f"file:{asset.id}",
                name=asset.original_filename or asset.filename,
                path=display_path,
                source=_source_from_path(display_path, asset.purpose or "upload"),
                size=asset.size,
                updated_at=asset.updated_at.isoformat() if asset.updated_at else None,
                mime_type=asset.content_type,
                download_url=f"/api/v1/workspaces/{workspace_id}/files/download?node_id=file:{asset.id}",
                preview_url=f"/api/v1/workspaces/{workspace_id}/files/preview?node_id=file:{asset.id}",
            )
        )
    return nodes


def _artifact_nodes(db: Session, workspace_id: str) -> list[WorkspaceFileNode]:
    conversation_ids = {item.id for item in _workspace_conversations(db, workspace_id)}
    artifacts = db.scalars(
        select(Artifact).where(Artifact.conversation_id.in_(conversation_ids), Artifact.deleted_at.is_(None))
    ).all()
    nodes: list[WorkspaceFileNode] = []
    for artifact in artifacts:
        content = artifact.content or {}
        fmt = content.get("format") or (content.get("tool_output") or {}).get("format") or "html"
        filename = content.get("filename") or f"{artifact.name}.{fmt}"
        nodes.append(
            _file_node(
                id=f"artifact:{artifact.id}",
                name=filename,
                path=f"artifacts/{artifact.id}/{filename}",
                source="artifact",
                size=artifact.file_size or 0,
                updated_at=artifact.updated_at.isoformat() if artifact.updated_at else None,
                mime_type=content.get("media_type") or artifact.mime_type,
                download_url=f"/api/v1/artifacts/{artifact.id}/export?format={fmt}",
                preview_url=f"/api/v1/artifacts/{artifact.id}/preview",
            )
        )
    return nodes


def _project_nodes(db: Session, workspace_id: str) -> list[WorkspaceFileNode]:
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
                    path=f"projects/{project.name}/{path}",
                    source="project",
                    size=item.size,
                    updated_at=item.updated_at.isoformat() if item.updated_at else None,
                    mime_type=_guess_mime(path),
                    download_url=f"/api/v1/workspaces/{workspace_id}/files/download?node_id=project:{item.id}",
                    preview_url=f"/api/v1/workspaces/{workspace_id}/files/preview?node_id=project:{item.id}",
                )
            )
    return nodes


def _filesystem_nodes(workspace_id: str, root: Path, seen_paths: set[str]) -> list[WorkspaceFileNode]:
    nodes: list[WorkspaceFileNode] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        if relative_path.startswith("artifacts/"):
            continue
        if relative_path in seen_paths:
            continue
        stat = path.stat()
        nodes.append(
            _file_node(
                id=f"fs:{quote(relative_path, safe='')}",
                name=path.name,
                path=relative_path,
                source=_source_from_path(relative_path, "workspace"),
                size=stat.st_size,
                updated_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                mime_type=_guess_mime(path.name),
                download_url=f"/api/v1/workspaces/{workspace_id}/files/download?node_id=fs:{quote(relative_path, safe='')}",
                preview_url=f"/api/v1/workspaces/{workspace_id}/files/preview?node_id=fs:{quote(relative_path, safe='')}",
            )
        )
    return nodes


def _file_node(**kwargs: Any) -> WorkspaceFileNode:
    return WorkspaceFileNode(type="file", children=[], **kwargs)


def _workspace_conversations(db: Session, workspace_id: str) -> list[Conversation]:
    conversations = db.scalars(select(Conversation).where(Conversation.deleted_at.is_(None))).all()
    return [
        item
        for item in conversations
        if isinstance(item.extra, dict)
        and str(item.extra.get("workspace_id") or item.extra.get("workspaceId") or "") == workspace_id
    ]


def _asset_in_workspace(asset: FileAsset, workspace_id: str, conversation_ids: set[str]) -> bool:
    extra = asset.extra if isinstance(asset.extra, dict) else {}
    return (
        str(extra.get("workspace_id") or "") == workspace_id
        or asset.conversation_id in conversation_ids
        or _path_under_workspace(asset.storage_path, workspace_id)
    )


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
    if not _asset_in_workspace(asset, workspace_id, {item.id for item in _workspace_conversations(db, workspace_id)}):
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


def _safe_workspace_file_path(workspace_id: str, encoded_path: str) -> Path:
    relative_path = normalize_relative_path(unquote(encoded_path))
    path = resolve_workspace_path(workspace_root(workspace_id), relative_path)
    if not path.exists() or not path.is_file():
        raise NotFoundError("文件不存在")
    return path


def _split_node_id(node_id: str) -> tuple[str, str]:
    if ":" not in node_id:
        raise ValidationAppError("node_id 格式不正确")
    kind, value = node_id.split(":", 1)
    if not value:
        raise ValidationAppError("node_id 格式不正确")
    return kind, value


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


def _source_from_path(path: str, fallback: str) -> str:
    first = path.split("/", 1)[0]
    return {
        "uploads": "upload",
        "files": "legacy",
        "artifacts": "artifact",
        "sandbox": "sandbox",
        "exports": "export",
        "projects": "project",
    }.get(first, fallback)


def _guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
