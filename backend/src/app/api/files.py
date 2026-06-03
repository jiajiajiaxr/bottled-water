from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import FileAsset, User, utcnow
from app.schemas.common import ApiResponse, FileAssetOut
from app.services.files import save_upload
from app.services.file_tools import (
    convert_file,
    embed_text,
    extract_text_from_path,
    preview_payload,
    summarize_text,
)
from app.services.serialization import file_asset_to_dict


router = APIRouter(tags=["files"])


async def _get_file(db: AsyncSession, user: User, file_id: str) -> FileAsset:
    asset = await db.scalar(
        select(FileAsset).where(FileAsset.id == file_id, FileAsset.deleted_at.is_(None))
    )
    if not asset:
        raise NotFoundError("文件不存在")
    if asset.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该文件")
    return asset


@router.post("/files/upload", response_model=ApiResponse[FileAssetOut])
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    purpose: str = Form("attachment"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await save_upload(
        db, user=user, upload=file, conversation_id=conversation_id, purpose=purpose
    )
    return ok(file_asset_to_dict(asset), "文件上传成功")


@router.post("/files", response_model=ApiResponse[FileAssetOut])
async def upload_file_alias(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(None),
    purpose: str = Form("attachment"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await upload_file(file, conversation_id, purpose, db, user)


@router.get("/files", response_model=ApiResponse[dict])
async def list_files(
    conversation_id: str | None = None,
    purpose: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(FileAsset).where(FileAsset.owner_id == user.id, FileAsset.deleted_at.is_(None))
    if conversation_id:
        query = query.where(FileAsset.conversation_id == conversation_id)
    if purpose:
        query = query.where(FileAsset.purpose == purpose)
    items = (await db.scalars(query.order_by(FileAsset.created_at.desc()))).all()
    return ok({"items": [file_asset_to_dict(item) for item in items], "total": len(items)})


@router.get("/files/{file_id}", response_model=ApiResponse[FileAssetOut])
async def get_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(file_asset_to_dict(await _get_file(db, user, file_id)))


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await _get_file(db, user, file_id)
    return FileResponse(
        asset.storage_path, media_type=asset.content_type, filename=asset.original_filename
    )


@router.post("/files/{file_id}/extract-text", response_model=ApiResponse[dict])
async def extract_file_text(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await _get_file(db, user, file_id)
    result = extract_text_from_path(
        Path(asset.storage_path),
        content_type=asset.content_type,
        filename=asset.original_filename,
    )
    asset.extracted_text = result["text"]
    asset.parse_status = result["status"]
    asset.extra = {
        **(asset.extra or {}),
        **(result.get("metadata") or {}),
        "tool_chain": ["file.extract_text"],
    }
    await db.commit()
    await db.refresh(asset)
    return ok(
        {"file": file_asset_to_dict(asset), "text": asset.extracted_text, "metadata": asset.extra}
    )


@router.get("/files/{file_id}/preview", response_model=ApiResponse[dict])
async def preview_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await _get_file(db, user, file_id)
    payload = preview_payload(
        Path(asset.storage_path),
        content_type=asset.content_type,
        filename=asset.original_filename,
    )
    return ok({**payload, "download_url": f"/api/v1/files/{asset.id}/download"})


@router.post("/files/{file_id}/summarize", response_model=ApiResponse[dict])
async def summarize_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await _get_file(db, user, file_id)
    text = asset.extracted_text
    if not text:
        result = extract_text_from_path(
            Path(asset.storage_path),
            content_type=asset.content_type,
            filename=asset.original_filename,
        )
        text = result["text"]
        asset.extracted_text = text
        asset.parse_status = result["status"]
        await db.commit()
    return ok({"file_id": asset.id, "summary": summarize_text(text or asset.original_filename)})


@router.post("/files/{file_id}/embed", response_model=ApiResponse[dict])
async def embed_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await _get_file(db, user, file_id)
    text = asset.extracted_text or asset.original_filename
    vector = embed_text(text)
    asset.extra = {
        **(asset.extra or {}),
        "embedding": {"provider": "local-hash", "dimensions": len(vector)},
    }
    await db.commit()
    return ok(
        {
            "file_id": asset.id,
            "embedding": vector,
            "dimensions": len(vector),
            "provider": "local-hash",
        }
    )


@router.get("/files/{file_id}/convert")
async def convert_uploaded_file(
    file_id: str,
    format: str = "pdf",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await _get_file(db, user, file_id)
    generated = convert_file(
        Path(asset.storage_path),
        content_type=asset.content_type,
        filename=asset.original_filename,
        target_format=format,
    )
    return Response(
        content=generated.content,
        media_type=generated.media_type,
        headers={"Content-Disposition": f'attachment; filename="{generated.filename}"'},
    )


@router.delete("/files/{file_id}", response_model=ApiResponse[dict])
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = await _get_file(db, user, file_id)
    asset.deleted_at = utcnow()
    await db.commit()
    return ok({"id": asset.id, "deleted": True})
