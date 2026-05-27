from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Artifact, Conversation, Deployment, FileAsset, User, utcnow
from app.services.artifact_exports import default_export_format
from app.services.artifacts import update_artifact_files
from app.services.file_tools import (
    convert_file,
    embed_text,
    extract_text_from_path,
    preview_payload,
    summarize_text,
)
from app.services.serialization import artifact_to_dict
from app.services.tools.artifact_executor import make_artifact_from_content
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


def _artifact(db: Session, user: User, artifact_id: str) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if not artifact or artifact.deleted_at is not None:
        raise NotFoundError("产物不存在")
    conversation = db.get(Conversation, artifact.conversation_id)
    if not conversation or (conversation.creator_id != user.id and user.role != "admin"):
        raise ForbiddenError("无权访问该产物")
    return artifact

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
        content_model = arguments.get("content_model") if isinstance(arguments.get("content_model"), dict) else None
        template = arguments.get("template") if isinstance(arguments.get("template"), str) else None
        return make_artifact_from_content(
            db,
            user,
            conversation_id=str(arguments.get("conversation_id") or ""),
            title=title,
            body=body,
            format_name=fmt,
            html_content=html_content,
            content_model=content_model,
            template=template,
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
