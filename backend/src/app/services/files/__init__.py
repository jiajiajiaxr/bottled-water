from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ValidationAppError
from app.services.tools.builtins.file import extract_text_from_path
from app.services.workspaces.filesystem import scoped_dir, workspace_id_from_conversation
from db.models import AuditLog, FileAsset, KnowledgeBase, KnowledgeDocument, User


SAFE_NAME = re.compile(r"[^a-zA-Z0-9._\-\u4e00-\u9fff]+")

ALLOWED_UPLOAD_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".tsv",
    ".html",
    ".htm",
    ".xml",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".css",
    ".scss",
    ".zip",
}

BLOCKED_UPLOAD_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".ps1",
    ".msi",
    ".com",
    ".scr",
    ".vbs",
    ".lnk",
    ".reg",
}

ALLOWED_UPLOAD_CONTENT_TYPES = {
    "application/pdf",
    "application/json",
    "application/xml",
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/css",
    "text/csv",
    "text/javascript",
    "application/javascript",
}


async def ensure_extension_tables(db: AsyncSession) -> None:
    for table in (
        FileAsset.__table__,
        KnowledgeBase.__table__,
        KnowledgeDocument.__table__,
        AuditLog.__table__,
    ):
        await db.run_sync(lambda session: table.create(bind=session.get_bind(), checkfirst=True))


def safe_filename(name: str) -> str:
    cleaned = SAFE_NAME.sub("_", name).strip("._")
    return cleaned or "upload.bin"


def validate_upload_type(filename: str, content_type: str | None) -> None:
    suffix = Path(filename).suffix.lower()
    mime = (content_type or "").split(";")[0].strip().lower()
    if suffix in BLOCKED_UPLOAD_EXTENSIONS:
        raise ValidationAppError(f"暂不支持上传该文件类型：{suffix}")
    if suffix in ALLOWED_UPLOAD_EXTENSIONS:
        return
    if mime.startswith("image/") or mime.startswith("text/"):
        return
    if mime in ALLOWED_UPLOAD_CONTENT_TYPES:
        return
    raise ValidationAppError(
        "暂不支持上传该文件类型。支持文本、Markdown、JSON、CSV、HTML、PDF、Office 文档、图片、代码文件和 ZIP。"
    )


def attachment_path(file_asset: FileAsset) -> Path:
    path = Path(file_asset.storage_path)
    if not path.exists() or not path.is_file():
        raise ValidationAppError("文件内容不可用")
    return path


async def _resolve_upload_workspace_id(
    db: AsyncSession,
    *,
    conversation_id: str | None,
    workspace_id: str | None,
) -> str | None:
    if workspace_id or not conversation_id:
        return workspace_id
    if hasattr(db, "run_sync"):
        return await db.run_sync(
            lambda session: workspace_id_from_conversation(session, conversation_id)
        )
    return workspace_id_from_conversation(db, conversation_id)


async def save_upload(
    db: AsyncSession,
    *,
    user: User,
    upload: UploadFile,
    conversation_id: str | None = None,
    purpose: str = "attachment",
    workspace_id: str | None = None,
) -> FileAsset:
    await ensure_extension_tables(db)
    settings = get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    raw = await upload.read()
    if len(raw) > max_bytes:
        raise ValidationAppError(f"文件超过 {settings.max_upload_mb}MB 限制")
    checksum = hashlib.sha256(raw).hexdigest()
    name = safe_filename(upload.filename or "upload.bin")
    content_type = upload.content_type or "application/octet-stream"
    validate_upload_type(name, content_type)
    resolved_workspace_id = await _resolve_upload_workspace_id(
        db,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
    )
    if resolved_workspace_id:
        folder = scoped_dir(resolved_workspace_id, "uploads", conversation_id=conversation_id)
    else:
        folder = Path(settings.storage_dir) / "uploads" / user.id[:8]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{checksum[:12]}-{name}"
    path.write_bytes(raw)

    extracted_result = extract_text_from_path(path, content_type=content_type, filename=name)
    extracted = extracted_result["text"][:200_000]
    metadata = {
        "extension": Path(name).suffix.lower(),
        "tool_chain": ["file.upload", "file.extract_text"],
        **(extracted_result.get("metadata") or {}),
    }
    if resolved_workspace_id:
        metadata["workspace_id"] = resolved_workspace_id

    asset = FileAsset(
        owner_id=user.id,
        conversation_id=conversation_id,
        filename=name,
        original_filename=upload.filename or name,
        content_type=content_type,
        size=len(raw),
        checksum=checksum,
        storage_path=str(path),
        purpose=purpose,
        parse_status=extracted_result["status"],
        extracted_text=extracted,
        extra=metadata,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset
