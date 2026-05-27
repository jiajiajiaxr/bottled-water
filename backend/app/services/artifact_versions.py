from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Artifact, ArtifactVersion, Conversation, utcnow
from app.services.tools.builtins.artifact.storage import (
    BINARY_ARTIFACT_FORMATS,
    regenerate_binary_from_preview,
)


def sync_current_artifact_version(
    db: Session,
    artifact: Artifact,
    *,
    change_summary: str | None = None,
) -> None:
    version = db.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact.id,
            ArtifactVersion.version == artifact.current_version,
        )
    )
    checksum = ((artifact.content or {}).get("source_file") or {}).get("checksum")
    if version:
        version.content = artifact.content
        version.checksum = checksum
        if change_summary:
            version.change_summary = change_summary
        return
    db.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            version=artifact.current_version,
            content=artifact.content,
            change_summary=change_summary or "Artifact version snapshot",
            checksum=checksum,
        )
    )


def update_artifact_files(db: Session, artifact_id: str, files: dict[str, str], summary: str) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    next_version = artifact.current_version + 1
    next_content = _next_artifact_content(db, artifact, files, summary, next_version)
    artifact.content = next_content
    artifact.current_version = next_version
    artifact.file_size = int(next_content.get("file_size") or artifact.file_size or 0)
    artifact.mime_type = str(next_content.get("media_type") or artifact.mime_type)
    artifact.updated_at = utcnow()
    db.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            version=next_version,
            content=artifact.content,
            change_summary=summary,
            checksum=((artifact.content or {}).get("source_file") or {}).get("checksum"),
        )
    )
    db.commit()
    db.refresh(artifact)
    return artifact


def _next_artifact_content(
    db: Session,
    artifact: Artifact,
    files: dict[str, str],
    summary: str,
    next_version: int,
) -> dict:
    current_files = artifact.content.get("files") or {}
    preview_html = files.get("index.html") or artifact.content.get("preview_html") or ""
    next_content = {
        **artifact.content,
        "preview_html": preview_html,
        "previous_files": current_files,
        "files": files,
        "summary": summary,
    }
    format_name = str(
        next_content.get("format") or ((next_content.get("tool_output") or {}).get("format") or "")
    )
    if format_name in BINARY_ARTIFACT_FORMATS and preview_html:
        _sync_binary_file_from_preview(db, artifact, next_content, format_name, preview_html, next_version)
    return next_content


def _sync_binary_file_from_preview(
    db: Session,
    artifact: Artifact,
    next_content: dict,
    format_name: str,
    preview_html: str,
    next_version: int,
) -> None:
    conversation = db.get(Conversation, artifact.conversation_id)
    if not conversation:
        return
    next_content.update(
        regenerate_binary_from_preview(
            db,
            owner_id=conversation.creator_id,
            artifact=artifact,
            format_name=format_name,
            preview_html=preview_html,
            version=next_version,
        )
    )
    tool_output = dict(next_content.get("tool_output") or {})
    tool_output.update(
        {
            "format": format_name,
            "filename": next_content.get("filename"),
            "media_type": next_content.get("media_type"),
            "size": next_content.get("file_size"),
        }
    )
    next_content["tool_output"] = tool_output
