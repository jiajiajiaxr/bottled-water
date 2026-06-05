from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import User, Workspace
from app.services.files.workspace_access import (
    artifact,
    assert_workspace_access,
    file_asset,
    file_asset_target,
    project_file,
    safe_workspace_file_path,
    split_node_id,
    workspace_conversations,
)
from app.services.files.workspace_naming import guess_mime
from app.services.files.workspace_nodes import collect_workspace_file_root
from app.services.files.workspace_operations import (
    bulk_delete_workspace_file_nodes,
    create_workspace_folder,
    delete_workspace_file_node,
    move_workspace_file_nodes,
    rename_workspace_file_node,
    set_workspace_file_favorite,
)
from app.services.tools.builtins.artifact.export import export_artifact
from app.services.workspaces.filesystem import workspace_root

__all__ = [
    "workspace_file_tree",
    "get_workspace_file_target",
    "delete_workspace_file_node",
    "rename_workspace_file_node",
    "create_workspace_folder",
    "set_workspace_file_favorite",
    "move_workspace_file_nodes",
    "bulk_delete_workspace_file_nodes",
]


def workspace_file_tree(db: Session, user: User, workspace_id: str) -> dict[str, Any]:
    assert_workspace_access(db, user, workspace_id)
    conversations = workspace_conversations(db, workspace_id)
    tree = collect_workspace_file_root(
        db,
        user=user,
        workspace_id=workspace_id,
        root=workspace_root(workspace_id),
        conversations=conversations,
        favorites=_workspace_file_favorites(db, workspace_id),
    )
    root_dict = tree.to_dict()
    return {
        "workspace_id": workspace_id,
        "root": root_dict,
        "items": root_dict["children"],
        "stats": _tree_stats(root_dict),
    }


def get_workspace_file_target(db: Session, user: User, workspace_id: str, node_id: str) -> dict[str, Any]:
    assert_workspace_access(db, user, workspace_id)
    kind, value = split_node_id(node_id)
    if kind == "file":
        asset = file_asset(db, workspace_id, value)
        return file_asset_target(workspace_id, asset)
    if kind == "artifact":
        item = artifact(db, workspace_id, value)
        exported = export_artifact(item)
        return {
            "kind": kind,
            "artifact": item,
            "artifact_id": item.id,
            "artifact_type": item.type,
            "bytes": exported.content,
            "filename": exported.filename,
            "mime_type": exported.media_type,
        }
    if kind == "project":
        item = project_file(db, workspace_id, value)
        return {
            "kind": kind,
            "text": item.content,
            "filename": Path(item.path).name,
            "mime_type": guess_mime(item.path),
            "relative_path": f"projects/{item.path}",
        }
    if kind == "fs":
        path = safe_workspace_file_path(workspace_id, value)
        return {
            "kind": kind,
            "path": path,
            "filename": path.name,
            "mime_type": guess_mime(path.name),
            "relative_path": unquote(value),
        }
    raise NotFoundError("文件不存在")


def _workspace_file_favorites(db: Session, workspace_id: str) -> set[str]:
    workspace = db.get(Workspace, workspace_id)
    config = workspace.config if workspace and isinstance(workspace.config, dict) else {}
    return {str(item) for item in config.get("file_favorites") or []}


def _tree_stats(root: dict[str, Any]) -> dict[str, Any]:
    stats = {"file_count": 0, "directory_count": 0, "total_size": 0, "source_counts": {}}

    def visit(node: dict[str, Any]) -> None:
        if node.get("type") == "file":
            stats["file_count"] += 1
            stats["total_size"] += int(node.get("size") or 0)
            source = str(node.get("source") or "workspace")
            stats["source_counts"][source] = stats["source_counts"].get(source, 0) + 1
        else:
            stats["directory_count"] += 1
        for child in node.get("children") or []:
            visit(child)

    visit(root)
    stats["directory_count"] = max(0, stats["directory_count"] - 1)
    return stats
