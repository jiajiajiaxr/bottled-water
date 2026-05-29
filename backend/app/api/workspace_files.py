from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.deps import get_current_user
from app.models import User
from app.services.files.workspace_tree import (
    delete_workspace_file_node,
    get_workspace_file_target,
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
    if target.get("text") is not None:
        return ok(
            {
                "type": "text",
                "text": str(target.get("text") or "")[:200_000],
                "content_type": target.get("mime_type"),
                "download_url": f"/api/v1/workspaces/{workspace_id}/files/download?node_id={quote(node_id, safe=':')}",
            }
        )
    if target.get("bytes") is not None:
        return ok(
            {
                "type": "binary",
                "content_type": target.get("mime_type"),
                "filename": target.get("filename"),
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


def _attachment_header(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename)}"
