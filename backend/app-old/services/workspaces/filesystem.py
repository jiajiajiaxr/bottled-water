from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.models import Conversation, Workspace


WORKSPACE_AREAS = (
    "uploads",
    "files",
    "artifacts",
    "sandbox",
    "exports",
    "projects",
    "tools",
    "logs",
)

def workspace_id_from_conversation(db: Session, conversation_id: str | None) -> str | None:
    if not conversation_id:
        return None
    conversation = db.get(Conversation, conversation_id)
    if not conversation or not isinstance(conversation.extra, dict):
        return None
    value = conversation.extra.get("workspace_id") or conversation.extra.get("workspaceId")
    return str(value) if value else None


def workspace_id_from_args(db: Session, arguments: dict[str, Any]) -> str:
    explicit = arguments.get("workspace_id") or arguments.get("workspaceId")
    if explicit:
        return safe_segment(str(explicit), default="default")
    return safe_segment(
        workspace_id_from_conversation(db, str(arguments.get("conversation_id") or "")) or "default",
        default="default",
    )


def database_workspace_id_from_args(db: Session, arguments: dict[str, Any]) -> str | None:
    explicit = arguments.get("workspace_id") or arguments.get("workspaceId")
    if explicit and db.get(Workspace, str(explicit)):
        return str(explicit)
    workspace_id = workspace_id_from_conversation(db, str(arguments.get("conversation_id") or ""))
    if workspace_id and db.get(Workspace, workspace_id):
        return workspace_id
    return None


def workspace_root(workspace_id: str | None) -> Path:
    root = backend_var_dir() / "workspaces" / safe_segment(workspace_id or "default", default="default")
    for area in WORKSPACE_AREAS:
        (root / area).mkdir(parents=True, exist_ok=True)
    return root


def workspace_area(workspace_id: str | None, area: str) -> Path:
    if area not in WORKSPACE_AREAS:
        raise ValidationAppError(f"unknown workspace area: {area}")
    path = workspace_root(workspace_id) / area
    path.mkdir(parents=True, exist_ok=True)
    return path


def scoped_dir(
    workspace_id: str | None,
    area: str,
    *,
    conversation_id: str | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
) -> Path:
    path = workspace_area(workspace_id, area)
    for label, value in (("conversations", conversation_id), ("agents", agent_id), ("tasks", task_id)):
        if value:
            path = path / label / safe_segment(value)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_workspace_path(base: Path, relative_path: str, *, allow_empty: bool = False) -> Path:
    clean = normalize_relative_path(relative_path, allow_empty=allow_empty)
    target = (base / clean).resolve() if clean else base.resolve()
    root = base.resolve()
    if target != root and root not in target.parents:
        raise ValidationAppError("path escapes workspace directory")
    return target


def normalize_relative_path(value: str, *, allow_empty: bool = False) -> str:
    raw = (value or "").strip().replace("\\", "/")
    if not raw:
        if allow_empty:
            return ""
        raise ValidationAppError("path cannot be empty")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ValidationAppError("absolute paths are not allowed")
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValidationAppError("parent directory traversal is not allowed")
    return "/".join(safe_segment(part) for part in parts)


def safe_segment(value: str | None, *, default: str = "item") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", str(value or "")).strip(".-_")
    return cleaned[:120] or default


def list_files(root: Path, *, limit: int = 80) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if len(items) >= limit:
            break
        if path.is_file():
            items.append({
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "updated_at": path.stat().st_mtime,
            })
    return items


def backend_var_dir() -> Path:
    root = Path(__file__).resolve().parents[3] / "var"
    root.mkdir(parents=True, exist_ok=True)
    return root
