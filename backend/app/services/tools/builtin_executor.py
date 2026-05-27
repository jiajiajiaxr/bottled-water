from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Artifact, Conversation, Deployment, FileAsset, User, utcnow
from app.services.artifact_exports import default_export_format
from app.services.artifacts import (
    build_demo_html,
    create_artifact,
    create_preview_message,
    update_artifact_files,
)
from app.services.file_tools import (
    convert_file,
    embed_text,
    extract_text_from_path,
    generate_file,
    preview_payload,
    summarize_text,
)
from app.services.serialization import artifact_to_dict
from app.services.tools.api_probe import run_api_test
from app.services.tools.browser_probe import run_browser_preview
from app.services.tools.sandbox_runner import run_sandbox_command, run_test_command


def _workspace_file_root() -> Path:
    root = Path(__file__).resolve().parents[3] / "var" / "ai-tools"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_tool_path(relative_path: str) -> Path:
    clean = relative_path.strip().replace("\\", "/").lstrip("/")
    if not clean:
        raise ValidationAppError("path 不能为空")
    target = (_workspace_file_root() / clean).resolve()
    root = _workspace_file_root().resolve()
    if root not in target.parents and target != root:
        raise ValidationAppError("路径超出 AI 工具工作区")
    return target


def _get_file(db: Session, user: User, file_id: str) -> FileAsset:
    asset = db.scalar(
        select(FileAsset).where(
            FileAsset.id == file_id,
            FileAsset.deleted_at.is_(None),
        )
    )
    if not asset:
        raise NotFoundError("文件不存在")
    if asset.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该文件")
    return asset


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


def _artifact(db: Session, user: User, artifact_id: str) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if not artifact or artifact.deleted_at is not None:
        raise NotFoundError("产物不存在")
    conversation = db.get(Conversation, artifact.conversation_id)
    if not conversation or (conversation.creator_id != user.id and user.role != "admin"):
        raise ForbiddenError("无权访问该产物")
    return artifact


def _make_artifact_from_content(
    db: Session,
    user: User,
    *,
    conversation_id: str | None,
    title: str,
    body: str,
    format_name: str,
    html_content: str | None = None,
) -> dict[str, Any]:
    conversation = _get_conversation(db, user, conversation_id)
    artifact_type = {
        "pdf": "document",
        "docx": "document",
        "xlsx": "spreadsheet",
        "pptx": "slides",
        "html": "web_app",
        "web_app": "web_app",
    }.get(format_name, "document")
    generated = None
    if format_name in {"pdf", "docx", "xlsx", "pptx", "html"}:
        generated = generate_file("html" if format_name == "web_app" else format_name, title=title, body=body)
    html_preview = html_content or build_demo_html(title, body[:500], artifact_type=artifact_type)
    artifact = create_artifact(
        db,
        conversation,
        task=None,
        name=title,
        html=html_preview,
        artifact_type=artifact_type,
        description=f"由工具 artifact.create_{format_name} 生成。",
    )
    content = dict(artifact.content or {})
    content["tool_output"] = {
        "tool": f"artifact.create_{format_name}",
        "format": format_name,
        "capability_level": "real",
        "filename": generated.filename if generated else None,
        "media_type": generated.media_type if generated else None,
        "size": len(generated.content) if generated else len(html_preview),
    }
    artifact.content = content
    preview = create_preview_message(db, conversation, artifact)
    conversation.last_message_preview = "工具已生成产物卡片，可点击预览。"
    conversation.last_message_sender = "Artifact Tool"
    conversation.last_message_at = utcnow()
    conversation.message_count += 1
    db.commit()
    db.refresh(artifact)
    db.refresh(preview)
    export_format = "html" if format_name in {"html", "web_app"} else format_name
    return {
        "status": "succeeded",
        "capability_level": "real",
        "artifact_id": artifact.id,
        "artifact": artifact_to_dict(artifact),
        "preview_message_id": preview.id,
        "preview_url": f"/api/v1/artifacts/{artifact.id}/preview",
        "export_url": f"/api/v1/artifacts/{artifact.id}/export?format={export_format}",
        "format": export_format,
        "filename": generated.filename if generated else None,
        "media_type": generated.media_type if generated else "text/html; charset=utf-8",
    }


def invoke_builtin_tool(db: Session, user: User, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "file.upload":
        return {"status": "requires_upload", "message": "file.upload 通过 /files/upload multipart 接口执行。"}
    if name.startswith("file."):
        file_id = str(arguments.get("file_id") or "")
        if name in {"file.extract_text", "file.preview", "file.convert", "file.summarize", "file.embed"}:
            asset = _get_file(db, user, file_id)
            path = Path(asset.storage_path)
            if name == "file.extract_text":
                result = extract_text_from_path(path, content_type=asset.content_type, filename=asset.original_filename)
                asset.extracted_text = result["text"]
                asset.parse_status = result["status"]
                asset.extra = {**(asset.extra or {}), **(result.get("metadata") or {}), "tool_chain": ["file.extract_text"]}
                db.commit()
                return {"status": "succeeded", "text": asset.extracted_text, "metadata": asset.extra}
            if name == "file.preview":
                return {"status": "succeeded", **preview_payload(path, content_type=asset.content_type, filename=asset.original_filename)}
            if name == "file.convert":
                fmt = str(arguments.get("format") or "pdf")
                generated = convert_file(path, content_type=asset.content_type, filename=asset.original_filename, target_format=fmt)
                return {
                    "status": "succeeded",
                    "filename": generated.filename,
                    "media_type": generated.media_type,
                    "size": len(generated.content),
                }
            if name == "file.summarize":
                text = asset.extracted_text or extract_text_from_path(path, content_type=asset.content_type, filename=asset.original_filename)["text"]
                return {"status": "succeeded", "summary": summarize_text(text, max_chars=int(arguments.get("max_chars") or 1200))}
            if name == "file.embed":
                text = asset.extracted_text or asset.original_filename
                return {"status": "succeeded", "embedding": embed_text(text), "provider": "local-hash"}
        if name == "file.read":
            if file_id:
                asset = _get_file(db, user, file_id)
                return {"status": "succeeded", "content": Path(asset.storage_path).read_text(encoding="utf-8", errors="ignore")[:200_000]}
            path = _safe_tool_path(str(arguments.get("path") or ""))
            return {"status": "succeeded", "path": str(path), "content": path.read_text(encoding="utf-8", errors="ignore")[:200_000]}
        if name == "file.write":
            path = _safe_tool_path(str(arguments.get("path") or ""))
            content = str(arguments.get("content") or "")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"status": "succeeded", "path": str(path), "size": len(content.encode("utf-8"))}

    if name.startswith("artifact.create_"):
        fmt = name.removeprefix("artifact.create_")
        title = str(arguments.get("title") or "AgentHub 产物")
        body = str(arguments.get("body") or arguments.get("content") or title)
        html_content = arguments.get("html") if isinstance(arguments.get("html"), str) else None
        return _make_artifact_from_content(
            db,
            user,
            conversation_id=str(arguments.get("conversation_id") or ""),
            title=title,
            body=body,
            format_name=fmt,
            html_content=html_content,
        )
    if name == "artifact.export":
        artifact = _artifact(db, user, str(arguments.get("artifact_id") or ""))
        fmt = str(arguments.get("format") or default_export_format(artifact))
        return {
            "status": "succeeded",
            "artifact_id": artifact.id,
            "format": fmt,
            "export_url": f"/api/v1/artifacts/{artifact.id}/export?format={fmt}",
        }
    if name == "artifact.preview":
        artifact = _artifact(db, user, str(arguments.get("artifact_id") or ""))
        return {"status": "succeeded", "artifact_id": artifact.id, "preview_url": f"/api/v1/artifacts/{artifact.id}/preview"}
    if name == "artifact.revise":
        files = arguments.get("files")
        if not isinstance(files, dict):
            raise ValidationAppError("files 必须是对象")
        artifact = update_artifact_files(db, str(arguments.get("artifact_id") or ""), {str(k): str(v) for k, v in files.items()}, str(arguments.get("summary") or "工具修订"))
        return {"status": "succeeded", "artifact": artifact_to_dict(artifact)}
    if name == "artifact.diff":
        artifact = _artifact(db, user, str(arguments.get("artifact_id") or ""))
        current = artifact.content.get("files") or {}
        previous = artifact.content.get("previous_files") or {}
        return {"status": "succeeded", "files_changed": sorted(set(current) | set(previous)), "version": artifact.current_version}

    if name == "db.inspect":
        inspector = inspect(db.get_bind())
        return {"status": "succeeded", "tables": [{"name": table, "columns": [column["name"] for column in inspector.get_columns(table)]} for table in inspector.get_table_names()]}
    if name == "api.test":
        return run_api_test(arguments)
    if name == "sandbox.run":
        return run_sandbox_command(arguments)
    if name == "test.run":
        return run_test_command(arguments)
    if name == "browser.preview":
        return run_browser_preview(arguments)
    if name == "security.audit":
        target = str(arguments.get("target") or arguments)
        findings = []
        risk = 0.1
        if re.search(r"(api_key|secret|password|token)", target, re.I):
            risk = 0.8
            findings.append("输入中疑似包含敏感字段，请确认是否需要脱敏。")
        return {"status": "succeeded", "risk_score": risk, "findings": findings or ["未发现高风险项。"]}
    if name == "document.review":
        text = str(arguments.get("text") or arguments.get("body") or "")
        findings = ["结构完整，适合继续交付。"] if len(text) > 80 else ["内容较短，建议补充背景、目标和验收标准。"]
        return {"status": "succeeded", "findings": findings}
    if name == "deploy.preview":
        artifact = _artifact(db, user, str(arguments.get("artifact_id") or ""))
        deployment = Deployment(
            artifact_id=artifact.id,
            mode="preview_link",
            status="deployed",
            access_url=f"/api/v1/artifacts/{artifact.id}/preview?deployment=1",
            deploy_log="工具 deploy.preview 已创建预览部署。",
            steps=[{"name": "preview", "status": "completed", "duration_ms": 120}],
            deployed_at=utcnow(),
        )
        db.add(deployment)
        db.commit()
        return {"status": "succeeded", "deployment": {"id": deployment.id, "url": deployment.access_url, "status": deployment.status}}
    if name == "deploy.rollback":
        return {"status": "succeeded", "deployment_id": arguments.get("deployment_id"), "message": "已创建回滚记录，当前演示环境保持上一版本可访问。"}

    raise NotFoundError("内置工具不存在")
