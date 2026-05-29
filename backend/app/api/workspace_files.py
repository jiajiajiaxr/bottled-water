from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.deps import get_current_user
from app.models import User
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


router = APIRouter(tags=["workspace-files"])


@router.get("/workspaces/{workspace_id}/files/tree")
async def get_workspace_file_tree(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(workspace_file_tree(db, user, workspace_id))


@router.get("/workspaces/{workspace_id}/files/download")
async def download_workspace_file(
    workspace_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = get_workspace_file_target(db, user, workspace_id, node_id)
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


@router.get("/workspaces/{workspace_id}/files/preview")
async def preview_workspace_file(
    workspace_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = get_workspace_file_target(db, user, workspace_id, node_id)
    if target.get("kind") == "artifact":
        return ok(_artifact_preview_payload(workspace_id, node_id, target))
    if target.get("text") is not None:
        content_type = str(target.get("mime_type") or "text/plain")
        return ok(
            {
                "type": "file_preview",
                "mode": _preview_mode(content_type, str(target.get("filename") or "")),
                "text": str(target.get("text") or "")[:200_000],
                "preview_text": str(target.get("text") or "")[:200_000],
                "content_type": content_type,
                "filename": target.get("filename"),
                "download_url": f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}",
            }
        )
    if target.get("bytes") is not None:
        content = target.get("bytes")
        content_type = str(target.get("mime_type") or "application/octet-stream")
        filename = str(target.get("filename") or "")
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
            }
        )
    path = Path(str(target["path"]))
    payload = preview_payload(
        path,
        content_type=str(target.get("mime_type") or "application/octet-stream"),
        filename=str(target.get("filename") or path.name),
    )
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(delete_workspace_file_node(db, user, workspace_id, node_id))


@router.post("/workspaces/{workspace_id}/files/bulk-delete")
async def bulk_delete_workspace_files(
    workspace_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    node_ids = [str(item) for item in payload.get("node_ids") or []]
    return ok(bulk_delete_workspace_file_nodes(db, user, workspace_id, node_ids))


@router.patch("/workspaces/{workspace_id}/files")
async def rename_workspace_file(
    workspace_id: str,
    node_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(rename_workspace_file_node(db, user, workspace_id, node_id, str(payload.get("name") or "")))


@router.post("/workspaces/{workspace_id}/files/folders")
async def create_folder(
    workspace_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(
        create_workspace_folder(
            db,
            user,
            workspace_id,
            str(payload.get("parent_path") or "files"),
            str(payload.get("name") or ""),
        )
    )


@router.post("/workspaces/{workspace_id}/files/move")
async def move_files(
    workspace_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(
        move_workspace_file_nodes(
            db,
            user,
            workspace_id,
            [str(item) for item in payload.get("node_ids") or []],
            str(payload.get("target_path") or "files"),
        )
    )


@router.post("/workspaces/{workspace_id}/files/favorite")
async def favorite_file(
    workspace_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(
        set_workspace_file_favorite(
            db,
            user,
            workspace_id,
            str(payload.get("node_id") or ""),
            bool(payload.get("favorite")),
        )
    )


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


def _artifact_preview_payload(workspace_id: str, node_id: str, target: dict[str, Any]) -> dict[str, Any]:
    artifact = target["artifact"]
    content = artifact.content or {}
    filename = str(target.get("filename") or content.get("filename") or artifact.name)
    content_type = str(target.get("mime_type") or content.get("media_type") or artifact.mime_type)
    download_url = f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}"
    preview_url = f"/api/v1/artifacts/{artifact.id}/preview"
    mode = _preview_mode(content_type, filename)
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
