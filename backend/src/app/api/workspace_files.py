from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypeVar
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.services.files.previewers.office import build_office_preview, is_office_file
from app.services.files.workspace_tree import (
    bulk_delete_workspace_file_nodes,
    create_workspace_folder,
    delete_workspace_file_node,
    get_workspace_file_target,
    move_workspace_file_nodes,
    rename_workspace_file_node,
    set_workspace_file_favorite,
    workspace_file_tree,
)
from app.services.tools.builtins.file.preview import preview_payload
from db import get_db
from db.models import User


router = APIRouter(tags=["workspace-files"])

T = TypeVar("T")


async def _sync_call(db: Any, fn: Callable[[Any], T]) -> T:
    if hasattr(db, "run_sync"):
        return await db.run_sync(fn)
    return fn(db)


@router.get("/workspaces/{workspace_id}/files/tree")
async def get_workspace_file_tree(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await _sync_call(db, lambda session: workspace_file_tree(session, user, workspace_id))
    return ok(data)


@router.get("/workspaces/{workspace_id}/files/download")
async def download_workspace_file(
    workspace_id: str,
    node_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = await _sync_call(db, lambda session: get_workspace_file_target(session, user, workspace_id, node_id))
    filename = str(target.get("filename") or "workspace-file")
    media_type = str(target.get("mime_type") or "application/octet-stream")
    if target.get("path"):
        return FileResponse(str(target["path"]), media_type=media_type, filename=filename)
    content = target.get("bytes")
    if isinstance(content, bytes):
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": _attachment_header(filename)},
        )
    text = str(target.get("text") or "")
    return Response(
        content=text.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": _attachment_header(filename)},
    )


@router.get("/workspaces/{workspace_id}/files/preview-pdf")
async def download_workspace_file_preview_pdf(
    workspace_id: str,
    node_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = await _sync_call(db, lambda session: get_workspace_file_target(session, user, workspace_id, node_id))
    filename = str(target.get("filename") or "workspace-file")
    media_type = str(target.get("mime_type") or "application/octet-stream")
    result = build_office_preview(
        workspace_id=workspace_id,
        node_id=node_id,
        target=target,
        filename=filename,
        mime_type=media_type,
    )
    if not result.preview_pdf_path:
        raise ValidationAppError(result.error or "Office PDF 预览生成失败")
    return FileResponse(
        str(result.preview_pdf_path),
        media_type="application/pdf",
        filename=f"{Path(filename).stem or 'preview'}.preview.pdf",
    )


@router.get("/workspaces/{workspace_id}/files/preview")
async def preview_workspace_file(
    workspace_id: str,
    node_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = await _sync_call(db, lambda session: get_workspace_file_target(session, user, workspace_id, node_id))
    if target.get("kind") == "artifact":
        return ok(_artifact_preview_payload(workspace_id, node_id, target))
    if target.get("text") is not None:
        content_type = str(target.get("mime_type") or "text/plain")
        text = str(target.get("text") or "")[:200_000]
        return ok(
            {
                "type": "file_preview",
                "mode": _preview_mode(content_type, str(target.get("filename") or "")),
                "text": text,
                "preview_text": text,
                "content_type": content_type,
                "filename": target.get("filename"),
                "download_url": f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}",
            }
        )
    if target.get("bytes") is not None:
        content = target.get("bytes")
        content_type = str(target.get("mime_type") or "application/octet-stream")
        filename = str(target.get("filename") or "")
        if is_office_file(content_type, filename):
            return ok(_office_preview_payload(workspace_id, node_id, target, filename, content_type))
        if isinstance(content, bytes) and _is_text_preview(content_type, filename):
            text = content.decode("utf-8", errors="replace")
            return ok(
                {
                    "type": "file_preview",
                    "mode": _preview_mode(content_type, filename),
                    "text": text[:200_000],
                    "preview_text": text[:200_000],
                    "content_type": content_type,
                    "filename": filename,
                    "download_url": f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}",
                }
            )
        return ok(
            {
                "type": "file_preview",
                "mode": _preview_mode(content_type, filename),
                "content_type": content_type,
                "filename": filename,
                "download_url": f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}",
                "preview_error": "不支持在线预览，请下载原文件查看。",
            }
        )
    path = Path(str(target["path"]))
    content_type = str(target.get("mime_type") or "application/octet-stream")
    filename = str(target.get("filename") or path.name)
    if is_office_file(content_type, filename):
        return ok(_office_preview_payload(workspace_id, node_id, target, filename, content_type))
    payload = preview_payload(path, content_type=content_type, filename=filename)
    return ok(
        {
            **payload,
            "type": "file_preview",
            "download_url": f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}",
        }
    )


@router.delete("/workspaces/{workspace_id}/files")
async def delete_workspace_file(
    workspace_id: str,
    node_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await _sync_call(db, lambda session: delete_workspace_file_node(session, user, workspace_id, node_id))
    return ok(data)


@router.post("/workspaces/{workspace_id}/files/bulk-delete")
async def bulk_delete_workspace_files(
    workspace_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    node_ids = [str(item) for item in payload.get("node_ids") or []]
    data = await _sync_call(db, lambda session: bulk_delete_workspace_file_nodes(session, user, workspace_id, node_ids))
    return ok(data)


@router.patch("/workspaces/{workspace_id}/files")
async def rename_workspace_file(
    workspace_id: str,
    node_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = str(payload.get("name") or "")
    data = await _sync_call(db, lambda session: rename_workspace_file_node(session, user, workspace_id, node_id, name))
    return ok(data)


@router.post("/workspaces/{workspace_id}/files/folders")
async def create_folder(
    workspace_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await _sync_call(
        db,
        lambda session: create_workspace_folder(
            session,
            user,
            workspace_id,
            str(payload.get("parent_path") or "files"),
            str(payload.get("name") or ""),
        ),
    )
    return ok(data)


@router.post("/workspaces/{workspace_id}/files/move")
async def move_files(
    workspace_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    node_ids = [str(item) for item in payload.get("node_ids") or []]
    target_path = str(payload.get("target_path") or "files")
    data = await _sync_call(
        db,
        lambda session: move_workspace_file_nodes(session, user, workspace_id, node_ids, target_path),
    )
    return ok(data)


@router.post("/workspaces/{workspace_id}/files/favorite")
async def favorite_file(
    workspace_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await _sync_call(
        db,
        lambda session: set_workspace_file_favorite(
            session,
            user,
            workspace_id,
            str(payload.get("node_id") or ""),
            bool(payload.get("favorite")),
        ),
    )
    return ok(data)


def _attachment_header(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename)}"


def _preview_mode(content_type: str, filename: str) -> str:
    normalized = content_type.lower()
    suffix = Path(filename).suffix.lower()
    if normalized.startswith("image/"):
        return "image"
    if "application/pdf" in normalized or suffix == ".pdf":
        return "pdf"
    if "html" in normalized or suffix in {".html", ".htm"}:
        return "html"
    if "markdown" in normalized or suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".docx", ".pptx", ".xlsx"} or "officedocument" in normalized:
        return "office_text"
    if normalized.startswith("text/") or "json" in normalized:
        return "text"
    return "binary"


def _is_text_preview(content_type: str, filename: str) -> bool:
    return _preview_mode(content_type, filename) in {"text", "html", "markdown"}


def _office_preview_payload(
    workspace_id: str,
    node_id: str,
    target: dict[str, Any],
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    download_url = f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}"
    preview_pdf_url = f"/api/v1/workspaces/{workspace_id}/files/preview-pdf?node_id={quote(node_id, safe=':')}"
    result = build_office_preview(
        workspace_id=workspace_id,
        node_id=node_id,
        target=target,
        filename=filename,
        mime_type=content_type,
    )
    if result.preview_pdf_path:
        preview_info: dict[str, Any] = {"cached": result.cached}
        if result.error:
            preview_info["warning"] = result.error
        return {
            "type": "file_preview",
            "mode": "pdf",
            "content_type": "application/pdf",
            "original_content_type": content_type,
            "filename": filename,
            "preview_pdf_url": preview_pdf_url,
            "preview_download_url": preview_pdf_url,
            "download_url": download_url,
            "office_preview": preview_info,
        }
    return {
        "type": "file_preview",
        "mode": "office_text",
        "content_type": content_type,
        "filename": filename,
        "text": result.fallback_text,
        "preview_text": result.fallback_text,
        "download_url": download_url,
        "preview_error": result.error or "当前环境无法生成 Office PDF 预览。",
    }


def _artifact_preview_payload(workspace_id: str, node_id: str, target: dict[str, Any]) -> dict[str, Any]:
    artifact = target["artifact"]
    content = artifact.content or {}
    filename = str(target.get("filename") or content.get("filename") or artifact.name)
    content_type = str(target.get("mime_type") or content.get("media_type") or artifact.mime_type)
    download_url = f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}"
    preview_url = f"/api/v1/artifacts/{artifact.id}/preview"
    mode = _preview_mode(content_type, filename)
    if is_office_file(content_type, filename):
        payload = _office_preview_payload(workspace_id, node_id, target, filename, content_type)
        payload["artifact_id"] = artifact.id
        payload["artifact_type"] = artifact.type
        payload["preview_url"] = preview_url
        return payload
    preview_html = _artifact_preview_html(content)
    if not preview_html and mode == "html" and isinstance(target.get("bytes"), bytes):
        preview_html = target["bytes"].decode("utf-8", errors="replace")
    if preview_html and mode in {"office_text", "html", "text", "binary"}:
        return {
            "type": "file_preview",
            "mode": "html",
            "text": preview_html[:500_000],
            "preview_text": preview_html[:500_000],
            "content_type": "text/html; charset=utf-8",
            "filename": filename,
            "artifact_id": artifact.id,
            "artifact_type": artifact.type,
            "preview_url": preview_url,
            "download_url": download_url,
        }
    return {
        "type": "file_preview",
        "mode": mode,
        "content_type": content_type,
        "filename": filename,
        "artifact_id": artifact.id,
        "artifact_type": artifact.type,
        "preview_url": preview_url,
        "download_url": download_url,
        "preview_error": "" if mode in {"pdf", "image"} else "不支持在线预览，请下载原文件查看。",
    }


def _artifact_preview_html(content: dict[str, Any]) -> str:
    files = content.get("files") if isinstance(content.get("files"), dict) else {}
    return str(
        content.get("preview_html")
        or files.get("index.html")
        or content.get("html")
        or content.get("source_text")
        or content.get("summary")
        or ""
    )

