from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Artifact, ArtifactVersion, Conversation, Message, User, utcnow
from app.services.tools.builtins.artifact.renderers import build_content_model, render_preview_html
from app.services.tools.builtins.artifact.storage import (
    artifact_type_for_format,
    build_artifact_file,
    html_artifact_file,
    persist_artifact_file,
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
    if export_format == "html":
        _validate_agent_html(html_content)
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
    artifact = _create_artifact_record(
        db,
        conversation,
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
    _sync_current_artifact_version(db, artifact, change_summary="初始真实文件产物")
    preview = _create_preview_message(db, conversation, artifact)
    _touch_conversation(conversation)
    db.commit()
    db.refresh(artifact)
    db.refresh(preview)
    return _artifact_tool_result(artifact, preview.id, export_format, generated.filename, generated.media_type)


def _validate_agent_html(html_content: str | None) -> None:
    html = (html_content or "").strip()
    lower = html.lower()
    if not html:
        raise ValidationAppError("Agent 未提供真实 HTML 代码，已拒绝生成模板化 HTML 产物。请让 Agent 重新输出完整 HTML/CSS/JS。")
    if "<html" not in lower or "<body" not in lower:
        raise ValidationAppError("HTML 产物缺少完整 <html>/<body> 结构，已拒绝套用兜底模板。")
    if len(html) < 300:
        raise ValidationAppError("HTML 产物内容过短，可能不是可运行页面，已拒绝生成假预览卡片。")


def _create_artifact_record(
    db: Session,
    conversation: Conversation,
    *,
    name: str,
    html: str,
    artifact_type: str,
    description: str,
) -> Artifact:
    artifact = Artifact(
        conversation_id=conversation.id,
        type=artifact_type,
        name=name,
        description=description,
        status="published",
        storage_url="/api/v1/artifacts/preview-pending",
        content={
            "files": {"index.html": html},
            "previous_files": {"index.html": html.replace("AgentHub", "AgentHub v0")},
            "preview_html": html,
            "summary": "由 AgentHub 工具生成的真实文件产物。",
        },
        current_version=1,
        mime_type="text/html",
    )
    db.add(artifact)
    db.flush()
    artifact.storage_url = f"/api/v1/artifacts/{artifact.id}/preview"
    return artifact


def _sync_current_artifact_version(db: Session, artifact: Artifact, *, change_summary: str) -> None:
    existing = db.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact.id,
            ArtifactVersion.version == artifact.current_version,
        )
    )
    if existing:
        existing.content = artifact.content
        existing.change_summary = change_summary
        return
    db.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            version=artifact.current_version,
            content=artifact.content,
            change_summary=change_summary,
        )
    )


def _create_preview_message(db: Session, conversation: Conversation, artifact: Artifact) -> Message:
    content = artifact.content if isinstance(artifact.content, dict) else {}
    artifact_format = str(content.get("format") or artifact.type or "html")
    filename = str(content.get("filename") or f"{artifact.name}.{artifact_format}")
    media_type = str(content.get("media_type") or artifact.mime_type or "text/html")
    message = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=artifact.agent_id,
        sender_name="Master Agent",
        content_type="preview_card",
        content={
            "artifact_id": artifact.id,
            "title": artifact.name,
            "artifact_type": artifact.type,
            "preview_url": f"/api/v1/artifacts/{artifact.id}/preview",
            "export_url": f"/api/v1/artifacts/{artifact.id}/export?format={artifact_format}",
            "format": artifact_format,
            "filename": filename,
            "media_type": media_type,
            "file_count": len(artifact.content.get("files") or {}),
            "total_size": artifact.file_size,
        },
        status="completed",
    )
    db.add(message)
    return message


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
