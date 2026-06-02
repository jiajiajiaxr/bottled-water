from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Conversation, User, utcnow
from app.services.tools.builtins.artifact.renderers import build_content_model, render_preview_html
from app.services.tools.builtins.artifact.storage import (
    artifact_type_for_format,
    build_artifact_file,
    html_artifact_file,
    persist_artifact_file,
)
from app.services.artifacts import (
    create_artifact,
    create_preview_message,
    sync_current_artifact_version,
)
from app.services.serialization import artifact_to_dict


def make_artifact_from_content(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    title: str,
    body: str,
    format_name: str,
    html_content: str | None = None,
    content_model: dict[str, Any] | None = None,
    template: str | None = None,
) -> dict[str, Any]:
    conversation = _get_conversation(db, user, conversation_id)
    artifact_type = artifact_type_for_format(format_name)
    export_format = "html" if format_name in {"html", "web_app"} else format_name
    model_text = content_model.get("source_text") if isinstance(content_model, dict) else None
    source_text = body or str(model_text or title)
    normalized_model = build_content_model(
        export_format,
        title=title,
        source_text=source_text,
        content_model=content_model,
        template=template,
    )
    generated = (
        html_artifact_file(title=title, html_content=html_content)
        if export_format == "html" and html_content
        else build_artifact_file(
            format_name,
            title=title,
            body=source_text,
            content_model=normalized_model,
        )
    )
    html_preview = _preview_html(export_format, generated.content, normalized_model, html_content)
    artifact = create_artifact(
        db,
        conversation,
        task=None,
        name=title,
        html=html_preview,
        artifact_type=artifact_type,
        description=f"由工具 artifact.create_{format_name} 生成。",
    )
    source_file = persist_artifact_file(
        db,
        owner_id=user.id,
        artifact=artifact,
        generated=generated,
        format_name=export_format,
        version=artifact.current_version,
        role="source",
    )
    _attach_file_content(
        artifact,
        format_name,
        export_format,
        generated,
        html_preview,
        source_file,
        source_text,
        normalized_model,
    )
    sync_current_artifact_version(db, artifact, change_summary="初始真实文件产物")
    preview = create_preview_message(db, conversation, artifact)
    _touch_conversation(conversation)
    db.commit()
    db.refresh(artifact)
    db.refresh(preview)
    return _artifact_tool_result(artifact, preview.id, export_format, generated.filename, generated.media_type)


def _get_conversation(db: Session, user: User, conversation_id: str | None) -> Conversation:
    if not conversation_id:
        raise ValidationAppError("conversation_id 不能为空")
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    if conversation.creator_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该会话")
    return conversation


def _preview_html(
    format_name: str,
    generated_content: bytes,
    content_model: dict[str, Any],
    html_content: str | None,
) -> str:
    if format_name in {"html", "web_app"}:
        return html_content or generated_content.decode("utf-8", errors="ignore")
    return render_preview_html(format_name, content_model)


def _attach_file_content(
    artifact,
    format_name: str,
    export_format: str,
    generated,
    html_preview: str,
    source_file: dict[str, Any],
    source_text: str,
    content_model: dict[str, Any],
) -> None:
    content = dict(artifact.content or {})
    content.update(
        {
            "preview_html": html_preview,
            "format": export_format,
            "media_type": generated.media_type,
            "filename": generated.filename,
            "source_file": source_file,
            "export_file": source_file,
            "source_text": source_text,
            "content_model": content_model,
        }
    )
    content["tool_output"] = {
        "tool": f"artifact.create_{format_name}",
        "format": export_format,
        "capability_level": "real",
        "filename": generated.filename,
        "media_type": generated.media_type,
        "size": len(generated.content),
    }
    artifact.content = content
    artifact.mime_type = generated.media_type
    artifact.file_size = len(generated.content)


def _touch_conversation(conversation: Conversation) -> None:
    conversation.last_message_preview = "工具已生成产物卡片，可点击预览。"
    conversation.last_message_sender = "Artifact Tool"
    conversation.last_message_at = utcnow()
    conversation.message_count += 1


def _artifact_tool_result(
    artifact,
    preview_message_id: str,
    export_format: str,
    filename: str,
    media_type: str,
) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "capability_level": "real",
        "artifact_id": artifact.id,
        "artifact": artifact_to_dict(artifact),
        "preview_message_id": preview_message_id,
        "preview_url": f"/api/v1/artifacts/{artifact.id}/preview",
        "export_url": f"/api/v1/artifacts/{artifact.id}/export?format={export_format}",
        "format": export_format,
        "filename": filename,
        "media_type": media_type,
    }
