from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import FileAsset
from app.services.files import plaintext_file_path
from app.services.tools.builtins.file.extractors import (
    can_extract_text_from_path,
    extract_text_from_path,
)


def attachment_from_file_asset(file_asset: FileAsset) -> dict[str, Any]:
    return {
        "id": file_asset.id,
        "file_id": file_asset.id,
        "original_filename": file_asset.original_filename,
        "filename": file_asset.original_filename,
        "content_type": file_asset.content_type,
        "size": file_asset.size,
        "parse_status": file_asset.parse_status,
        "extracted_text": (file_asset.extracted_text or "")[:12000],
        "public_url": file_asset.public_url,
        "download_url": f"/api/v1/files/{file_asset.id}/download",
        "metadata": file_asset.extra or {},
    }


def refresh_attachment_text_if_needed(file_asset: FileAsset) -> None:
    if not _should_refresh_attachment_text(file_asset):
        return
    with plaintext_file_path(file_asset) as path:
        result = extract_text_from_path(
            path,
            content_type=file_asset.content_type,
            filename=file_asset.original_filename,
        )
    file_asset.extracted_text = result["text"]
    file_asset.parse_status = result["status"]
    file_asset.extra = {
        **(file_asset.extra or {}),
        **(result.get("metadata") or {}),
        "tool_chain": ["file.extract_text"],
    }


def _should_refresh_attachment_text(file_asset: FileAsset) -> bool:
    if (file_asset.extracted_text or "").strip():
        return False
    path = Path(file_asset.storage_path)
    if not path.is_file():
        return False
    return can_extract_text_from_path(
        path,
        content_type=file_asset.content_type,
        filename=file_asset.original_filename,
    )
