from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.models import Conversation, FileAsset, User
from app.services.context.attachments import readable_attachment_text
from app.services.files import plaintext_file_path
from app.services.tools.builtins.file.extractors import extract_text_from_path
from app.services.workspaces.filesystem import (
    normalize_relative_path,
    resolve_workspace_path,
    workspace_id_from_conversation,
    workspace_root,
)


FILE_REF_PATTERN = re.compile(r"@file\((?P<body>[^)]{1,1200})\)")
FILE_ID_PATTERN = re.compile(r"(?:^|\s)file_id=(?P<file_id>[A-Za-z0-9._:-]+)")


def parse_file_references(text: str) -> list[dict[str, str]]:
    references: list[dict[str, str]] = []
    for match in FILE_REF_PATTERN.finditer(text or ""):
        body = match.group("body").strip()
        file_id_match = FILE_ID_PATTERN.search(body)
        file_id = file_id_match.group("file_id") if file_id_match else ""
        path = FILE_ID_PATTERN.sub("", body).strip().strip("'\"")
        if path or file_id:
            references.append({"path": path, "file_id": file_id})
    return references


def file_reference_text(text: str, file_references: Any) -> str:
    parts: list[str] = []
    if "@file(" in (text or ""):
        parts.append(text)
    if isinstance(file_references, list):
        for item in file_references:
            markup = _file_reference_markup(item)
            if markup:
                parts.append(markup)
    return "\n".join(parts)


def _file_reference_markup(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    path = str(item.get("path") or "").strip()
    file_id = str(item.get("file_id") or item.get("id") or "").strip()
    if not path and not file_id:
        return ""
    body = path
    if file_id:
        body = f"{body} file_id={file_id}".strip()
    return f"@file({body})"


def resolve_file_reference_attachments(
    db: Session,
    *,
    user: User,
    conversation: Conversation,
    text: str,
    existing_file_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    workspace_id = workspace_id_from_conversation(db, conversation.id)
    if not workspace_id:
        return []
    existing = existing_file_ids or set()
    attachments: list[dict[str, Any]] = []
    for reference in parse_file_references(text):
        attachment = _resolve_one(db, user=user, workspace_id=workspace_id, reference=reference)
        if attachment["file_id"] in existing:
            continue
        existing.add(str(attachment["file_id"]))
        attachments.append(attachment)
    return attachments


def _resolve_one(db: Session, *, user: User, workspace_id: str, reference: dict[str, str]) -> dict[str, Any]:
    if reference.get("file_id"):
        asset = _file_asset(db, user, workspace_id, reference["file_id"])
        return _attachment_from_file_asset(asset, workspace_id)
    if reference.get("path"):
        return _attachment_from_workspace_path(workspace_id, reference["path"])
    raise ValidationAppError("文件引用格式不正确，请使用 @file(path) 或 @file(path file_id=xxx)")


def _file_asset(db: Session, user: User, workspace_id: str, file_id: str) -> FileAsset:
    asset = db.scalar(
        select(FileAsset).where(
            FileAsset.id == file_id,
            FileAsset.deleted_at.is_(None),
        )
    )
    if not asset:
        raise ValidationAppError(f"文件引用不存在：{file_id}")
    extra = asset.extra if isinstance(asset.extra, dict) else {}
    path_in_workspace = False
    try:
        Path(asset.storage_path).resolve().relative_to(workspace_root(workspace_id).resolve())
        path_in_workspace = True
    except ValueError:
        path_in_workspace = False
    if asset.owner_id != user.id and str(extra.get("workspace_id") or "") != workspace_id and not path_in_workspace:
        raise ValidationAppError(f"无权引用文件：{asset.original_filename}")
    return asset


def _attachment_from_file_asset(asset: FileAsset, workspace_id: str) -> dict[str, Any]:
    metadata = dict(asset.extra or {})
    extracted = readable_attachment_text(
        {
            "content_type": asset.content_type,
            "extracted_text": asset.extracted_text,
            "metadata": metadata,
        }
    )
    if not extracted and Path(asset.storage_path).is_file():
        with plaintext_file_path(asset) as path:
            result = extract_text_from_path(
                path,
                content_type=asset.content_type,
                filename=asset.original_filename,
            )
        extracted = result["text"]
        metadata = {**metadata, **(result.get("metadata") or {})}
        asset.extracted_text = extracted
        asset.parse_status = result["status"]
        asset.extra = {**metadata, "tool_chain": ["file.extract_text"]}
    return {
        "file_id": asset.id,
        "filename": asset.original_filename,
        "content_type": asset.content_type,
        "size": asset.size,
        "parse_status": asset.parse_status,
        "extracted_text": extracted[:12000],
        "metadata": {
            **metadata,
            "workspace_id": workspace_id,
            "reference_type": "workspace_file",
            "path": _workspace_relative_path(workspace_id, Path(asset.storage_path)),
        },
    }


def _attachment_from_workspace_path(workspace_id: str, raw_path: str) -> dict[str, Any]:
    relative_path = normalize_relative_path(raw_path)
    path = resolve_workspace_path(workspace_root(workspace_id), relative_path)
    if not path.exists() or not path.is_file():
        raise ValidationAppError(f"文件引用不存在：{relative_path}")
    content_type = _guess_mime(path.name)
    result = extract_text_from_path(path, content_type=content_type, filename=path.name)
    extracted = result["text"]
    return {
        "file_id": f"workspace:{relative_path}",
        "filename": path.name,
        "content_type": content_type,
        "size": path.stat().st_size,
        "parse_status": result["status"],
        "extracted_text": extracted[:12000],
        "metadata": {
            **(result.get("metadata") or {}),
            "workspace_id": workspace_id,
            "reference_type": "workspace_file",
            "path": relative_path,
        },
    }


def _workspace_relative_path(workspace_id: str, path: Path) -> str:
    try:
        return path.resolve().relative_to(workspace_root(workspace_id).resolve()).as_posix()
    except ValueError:
        return path.name


def _guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
