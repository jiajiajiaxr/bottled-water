from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.models import User, utcnow
from app.services.files.workspace_access import (
    artifact,
    assert_workspace_access,
    file_asset,
    project_file,
    safe_filename,
    safe_workspace_dir_path,
    safe_workspace_file_path,
    split_node_id,
)
from app.services.workspaces.filesystem import normalize_relative_path, resolve_workspace_path, workspace_root


def delete_workspace_file_node(db: Session, user: User, workspace_id: str, node_id: str) -> dict[str, Any]:
    assert_workspace_access(db, user, workspace_id)
    kind, value = split_node_id(node_id)
    if kind == "file":
        file_asset(db, workspace_id, value).deleted_at = utcnow()
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "artifact":
        artifact(db, workspace_id, value).deleted_at = utcnow()
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "project":
        db.delete(project_file(db, workspace_id, value))
        db.commit()
        return {"id": node_id, "deleted": True}
    if kind == "fs":
        safe_workspace_file_path(workspace_id, value).unlink(missing_ok=True)
        return {"id": node_id, "deleted": True}
    if kind == "dir":
        shutil.rmtree(safe_workspace_dir_path(workspace_id, value))
        return {"id": node_id, "deleted": True}
    raise NotFoundError("文件不存在")


def rename_workspace_file_node(db: Session, user: User, workspace_id: str, node_id: str, new_name: str) -> dict[str, Any]:
    assert_workspace_access(db, user, workspace_id)
    cleaned = safe_filename(new_name)
    kind, value = split_node_id(node_id)
    if kind == "file":
        asset = file_asset(db, workspace_id, value)
        asset.original_filename = cleaned
        asset.filename = cleaned
        db.commit()
        return _rename_result(node_id, cleaned)
    if kind == "artifact":
        item = artifact(db, workspace_id, value)
        content = dict(item.content or {})
        content["filename"] = cleaned
        item.name = Path(cleaned).stem
        item.content = content
        db.commit()
        return _rename_result(node_id, cleaned)
    if kind == "project":
        item = project_file(db, workspace_id, value)
        item.path = normalize_relative_path(str(Path(item.path).with_name(cleaned)))
        db.commit()
        return _rename_result(node_id, cleaned)
    if kind == "fs":
        _rename_path(safe_workspace_file_path(workspace_id, value), cleaned)
        return _rename_result(node_id, cleaned)
    if kind == "dir":
        _rename_path(safe_workspace_dir_path(workspace_id, value), cleaned)
        return _rename_result(node_id, cleaned)
    raise NotFoundError("文件不存在")


def create_workspace_folder(
    db: Session,
    user: User,
    workspace_id: str,
    parent_path: str,
    name: str,
) -> dict[str, Any]:
    assert_workspace_access(db, user, workspace_id)
    cleaned = safe_filename(name)
    parent = safe_workspace_dir_path(workspace_id, parent_path or "files", create=True)
    folder = resolve_workspace_path(parent, cleaned)
    folder.mkdir(parents=True, exist_ok=False)
    relative_path = folder.relative_to(workspace_root(workspace_id)).as_posix()
    return {"path": relative_path, "name": cleaned, "display_name": cleaned}


def set_workspace_file_favorite(
    db: Session,
    user: User,
    workspace_id: str,
    node_id: str,
    favorite: bool,
) -> dict[str, Any]:
    workspace = assert_workspace_access(db, user, workspace_id)
    config = dict(workspace.config or {})
    favorites = set(config.get("file_favorites") or [])
    if favorite:
        favorites.add(node_id)
    else:
        favorites.discard(node_id)
    config["file_favorites"] = sorted(favorites)
    workspace.config = config
    db.commit()
    return {"id": node_id, "favorite": favorite}


def move_workspace_file_nodes(
    db: Session,
    user: User,
    workspace_id: str,
    node_ids: list[str],
    target_path: str,
) -> dict[str, Any]:
    assert_workspace_access(db, user, workspace_id)
    target = safe_workspace_dir_path(workspace_id, target_path or "files", create=True)
    moved = [_move_one(db, workspace_id, node_id, target) for node_id in node_ids]
    db.commit()
    return {"moved": moved}


def bulk_delete_workspace_file_nodes(
    db: Session,
    user: User,
    workspace_id: str,
    node_ids: list[str],
) -> dict[str, Any]:
    deleted = [delete_workspace_file_node(db, user, workspace_id, node_id)["id"] for node_id in node_ids]
    return {"deleted": deleted}


def _rename_result(node_id: str, name: str) -> dict[str, str]:
    return {"id": node_id, "name": name, "display_name": name}


def _rename_path(path: Path, cleaned: str) -> Path:
    target = resolve_workspace_path(path.parent, cleaned)
    if target.exists():
        raise ValidationAppError("目标位置已存在同名文件")
    path.rename(target)
    return target


def _move_one(db: Session, workspace_id: str, node_id: str, target: Path) -> dict[str, Any]:
    kind, value = split_node_id(node_id)
    if kind == "file":
        asset = file_asset(db, workspace_id, value)
        new_path = _move_path(workspace_id, Path(asset.storage_path), target)
        asset.storage_path = str(new_path)
        return {"id": node_id, "path": new_path.relative_to(workspace_root(workspace_id)).as_posix()}
    if kind == "fs":
        new_path = _move_path(workspace_id, safe_workspace_file_path(workspace_id, value), target)
        return {"id": node_id, "path": new_path.relative_to(workspace_root(workspace_id)).as_posix()}
    if kind == "dir":
        new_path = _move_path(workspace_id, safe_workspace_dir_path(workspace_id, value), target)
        return {"id": node_id, "path": new_path.relative_to(workspace_root(workspace_id)).as_posix()}
    if kind == "artifact":
        item = artifact(db, workspace_id, value)
        content = dict(item.content or {})
        content["workspace_folder"] = target.relative_to(workspace_root(workspace_id)).as_posix()
        item.content = content
        return {"id": node_id, "path": f"{content['workspace_folder']}/{content.get('filename') or item.name}"}
    raise NotFoundError("文件不存在")


def _move_path(workspace_id: str, path: Path, target: Path) -> Path:
    root = workspace_root(workspace_id).resolve()
    source = path.resolve()
    source.relative_to(root)
    destination = resolve_workspace_path(target, source.name)
    if destination.exists():
        raise ValidationAppError("目标位置已存在同名文件")
    source.rename(destination)
    return destination
