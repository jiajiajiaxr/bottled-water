from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from typing import Any

from sqlalchemy.orm import Session

from app.models import Artifact, FileAsset
from app.services.tools.builtins.artifact.renderers import build_content_model
from app.services.tools.builtins.file.converters import GeneratedFile, generate_file
from app.services.workspaces.filesystem import scoped_dir, safe_segment, workspace_id_from_conversation


BINARY_ARTIFACT_FORMATS = {"pdf", "docx", "xlsx", "pptx"}

ARTIFACT_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "html": "text/html; charset=utf-8",
}

ARTIFACT_TYPES = {
    "pdf": "document",
    "docx": "document",
    "xlsx": "spreadsheet",
    "pptx": "slides",
    "html": "web_app",
    "web_app": "web_app",
}


class PreviewTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3", "p", "li", "tr", "section", "article", "div", "br"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        value = " ".join(self.parts)
        value = re.sub(r"\s*\n\s*", "\n", value)
        value = re.sub(r"[ \t]{2,}", " ", value)
        return value.strip()


def artifact_type_for_format(format_name: str) -> str:
    return ARTIFACT_TYPES.get(format_name.lower().strip("."), "document")


def preview_html_to_text(preview_html: str) -> str:
    parser = PreviewTextParser()
    parser.feed(preview_html or "")
    return parser.text()


def build_artifact_file(
    format_name: str,
    *,
    title: str,
    body: str,
    content_model: dict[str, Any] | None = None,
) -> GeneratedFile:
    fmt = "html" if format_name == "web_app" else format_name
    return generate_file(fmt, title=title, body=body, content_model=content_model)


def html_artifact_file(*, title: str, html_content: str) -> GeneratedFile:
    safe = _safe_filename(title, max_length=48) or "agenthub-artifact"
    return GeneratedFile(
        content=html_content.encode("utf-8"),
        media_type=ARTIFACT_MEDIA_TYPES["html"],
        filename=f"{safe}.html",
    )


def persist_artifact_file(
    db: Session,
    *,
    owner_id: str,
    artifact: Artifact,
    generated: GeneratedFile,
    format_name: str,
    version: int,
    role: str = "source",
) -> dict[str, Any]:
    raw = generated.content
    checksum = hashlib.sha256(raw).hexdigest()
    safe_name = _safe_filename(generated.filename, max_length=48)
    workspace_id = workspace_id_from_conversation(db, artifact.conversation_id)
    folder = scoped_dir(
        workspace_id,
        "artifacts",
        conversation_id=artifact.conversation_id,
    ) / safe_segment(artifact.id) / f"v{version}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{role}-{checksum[:12]}-{safe_name}"
    path.write_bytes(raw)

    asset = FileAsset(
        owner_id=owner_id,
        conversation_id=artifact.conversation_id,
        artifact_id=artifact.id,
        filename=safe_name,
        original_filename=generated.filename,
        content_type=generated.media_type,
        size=len(raw),
        checksum=checksum,
        storage_path=str(path),
        public_url="/api/v1/files/{file_id}/download",
        purpose="artifact_source",
        parse_status="generated",
        extracted_text="",
        extra={
            "artifact_id": artifact.id,
            "artifact_version": version,
            "format": format_name,
            "role": role,
        },
    )
    db.add(asset)
    db.flush()
    asset.public_url = f"/api/v1/files/{asset.id}/download"
    return file_descriptor(asset, format_name=format_name, version=version, role=role)


def file_descriptor(
    asset: FileAsset,
    *,
    format_name: str,
    version: int,
    role: str,
) -> dict[str, Any]:
    return {
        "file_asset_id": asset.id,
        "filename": asset.original_filename or asset.filename,
        "media_type": asset.content_type,
        "format": format_name,
        "size": asset.size,
        "checksum": asset.checksum,
        "storage_path": asset.storage_path,
        "download_url": asset.public_url or f"/api/v1/files/{asset.id}/download",
        "version": version,
        "role": role,
    }


def regenerate_binary_from_preview(
    db: Session,
    *,
    owner_id: str,
    artifact: Artifact,
    format_name: str,
    preview_html: str,
    version: int,
) -> dict[str, Any]:
    source_text = preview_html_to_text(preview_html) or artifact.description or artifact.name
    generated = build_artifact_file(format_name, title=artifact.name, body=source_text)
    descriptor = persist_artifact_file(
        db,
        owner_id=owner_id,
        artifact=artifact,
        generated=generated,
        format_name=format_name,
        version=version,
        role="source",
    )
    return {
        "source_file": descriptor,
        "export_file": descriptor,
        "filename": descriptor["filename"],
        "media_type": descriptor["media_type"],
        "file_size": descriptor["size"],
        "source_text": source_text,
        "content_model": build_content_model(format_name, title=artifact.name, source_text=source_text),
        "source_generation": "preview_html_fallback",
    }


def _safe_filename(name: str, *, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name).strip("._")
    cleaned = cleaned or "artifact.bin"
    if len(cleaned) <= max_length:
        return cleaned
    stem, dot, suffix = cleaned.rpartition(".")
    if dot and 0 < len(suffix) <= 12:
        stem_limit = max(8, max_length - len(suffix) - 1)
        stem = stem[:stem_limit].rstrip("._-") or "artifact"
        return f"{stem}.{suffix}"
    return cleaned[:max_length].rstrip("._-") or "artifact.bin"
