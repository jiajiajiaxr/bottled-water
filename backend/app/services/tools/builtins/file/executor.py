from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.models import FileAsset, User
from app.services.tools.builtins.file.converters import convert_file
from app.services.tools.builtins.file.extractors import embed_text, extract_text_from_path, summarize_text
from app.services.tools.builtins.file.preview import preview_payload
from app.services.workspaces.filesystem import resolve_workspace_path, scoped_dir, workspace_id_from_args


def invoke_file_tool(db: Session, user: User, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "file.upload":
        return {"status": "requires_upload", "message": "file.upload runs through the multipart /files/upload API."}
    file_id = str(arguments.get("file_id") or "")
    if name in {"file.extract_text", "file.preview", "file.convert", "file.summarize", "file.embed"}:
        return _invoke_file_asset_tool(db, user, name, arguments, file_id)
    if name == "file.read":
        return _read_workspace_file(db, user, arguments, file_id)
    if name == "file.write":
        return _write_workspace_file(db, arguments)
    raise NotFoundError("file tool not found")


def _read_workspace_file(
    db: Session,
    user: User,
    arguments: dict[str, Any],
    file_id: str,
) -> dict[str, Any]:
    if file_id:
        asset = _get_file(db, user, file_id)
        content = Path(asset.storage_path).read_text(encoding="utf-8", errors="ignore")[:200_000]
        return {"status": "succeeded", "file_id": asset.id, "content": content}
    path = _safe_tool_path(db, arguments)
    return {
        "status": "succeeded",
        "workspace_id": workspace_id_from_args(db, arguments),
        "path": str(path),
        "content": path.read_text(encoding="utf-8", errors="ignore")[:200_000],
    }


def _write_workspace_file(db: Session, arguments: dict[str, Any]) -> dict[str, Any]:
    path = _safe_tool_path(db, arguments)
    content = str(arguments.get("content") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "status": "succeeded",
        "workspace_id": workspace_id_from_args(db, arguments),
        "path": str(path),
        "relative_path": str(arguments.get("path") or ""),
        "size": len(content.encode("utf-8")),
    }


def _invoke_file_asset_tool(
    db: Session,
    user: User,
    name: str,
    arguments: dict[str, Any],
    file_id: str,
) -> dict[str, Any]:
    asset = _get_file(db, user, file_id)
    path = Path(asset.storage_path)
    if name == "file.extract_text":
        result = extract_text_from_path(path, content_type=asset.content_type, filename=asset.original_filename)
        asset.extracted_text = result["text"]
        asset.parse_status = result["status"]
        asset.extra = {**(asset.extra or {}), **(result.get("metadata") or {}), "tool_chain": ["file.extract_text"]}
        db.commit()
        return {"status": "succeeded", "text": asset.extracted_text, "metadata": asset.extra}
    if name == "file.preview":
        return {"status": "succeeded", **preview_payload(path, content_type=asset.content_type, filename=asset.original_filename)}
    if name == "file.convert":
        generated = convert_file(
            path,
            content_type=asset.content_type,
            filename=asset.original_filename,
            target_format=str(arguments.get("format") or "pdf"),
        )
        return {
            "status": "succeeded",
            "filename": generated.filename,
            "media_type": generated.media_type,
            "size": len(generated.content),
        }
    if name == "file.summarize":
        text = asset.extracted_text or extract_text_from_path(path, content_type=asset.content_type, filename=asset.original_filename)["text"]
        return {"status": "succeeded", "summary": summarize_text(text, max_chars=int(arguments.get("max_chars") or 1200))}
    text = asset.extracted_text or asset.original_filename
    return {"status": "succeeded", "embedding": embed_text(text), "provider": "local-hash"}


def _safe_tool_path(db: Session, arguments: dict[str, Any]) -> Path:
    root = scoped_dir(
        workspace_id_from_args(db, arguments),
        "sandbox",
        conversation_id=str(arguments.get("conversation_id") or "") or None,
        agent_id=str(arguments.get("agent_id") or "") or None,
        task_id=str(arguments.get("task_id") or "") or None,
    )
    return resolve_workspace_path(root, str(arguments.get("path") or ""))


def _get_file(db: Session, user: User, file_id: str) -> FileAsset:
    asset = db.scalar(select(FileAsset).where(FileAsset.id == file_id, FileAsset.deleted_at.is_(None)))
    if not asset:
        raise NotFoundError("file not found")
    if asset.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("no permission to access this file")
    return asset
