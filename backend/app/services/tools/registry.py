from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Artifact, Conversation, Deployment, FileAsset, ToolDefinition, User, utcnow
from app.services.artifacts import build_demo_html, create_artifact, create_preview_message, update_artifact_files
from app.services.artifact_exports import default_export_format
from app.services.file_tools import (
    convert_file,
    embed_text,
    extract_text_from_path,
    generate_file,
    preview_payload,
    summarize_text,
)
from app.services.serialization import artifact_to_dict, tool_definition_to_dict


@dataclass(frozen=True)
class BuiltinTool:
    name: str
    display_name: str
    category: str
    description: str
    permissions: tuple[str, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.name,
            "tool_id": self.name,
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "type": "builtin",
            "status": "active",
            "version": "1.0.0",
            "permissions": list(self.permissions),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "tags": list(self.tags),
            "config": {"builtin": True},
            "is_builtin": True,
        }


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


BUILTIN_TOOLS: dict[str, BuiltinTool] = {
    "file.upload": BuiltinTool(
        "file.upload",
        "上传文件",
        "file",
        "接收用户文件并写入 FileAsset，供消息、知识库和工具链复用。",
        ("file:upload",),
        _schema({"conversation_id": {"type": "string"}, "purpose": {"type": "string"}}),
        _schema({"file": {"type": "object"}}),
        ("upload", "attachment"),
    ),
    "file.extract_text": BuiltinTool(
        "file.extract_text",
        "提取文本",
        "file",
        "从 PDF、Word、Excel、PPT、Markdown、HTML、代码和图片入口提取可供模型读取的文本。",
        ("file:read",),
        _schema({"file_id": {"type": "string"}}, ["file_id"]),
        _schema({"text": {"type": "string"}, "metadata": {"type": "object"}}),
        ("pdf", "docx", "xlsx", "pptx", "ocr-entry"),
    ),
    "file.preview": BuiltinTool(
        "file.preview",
        "文件预览",
        "file",
        "返回文件预览文本、预览模式和下载地址。",
        ("file:read",),
        _schema({"file_id": {"type": "string"}}, ["file_id"]),
        _schema({"preview_text": {"type": "string"}, "mode": {"type": "string"}}),
    ),
    "file.convert": BuiltinTool(
        "file.convert",
        "文件转换",
        "file",
        "把上传文件转换为 PDF、DOCX、XLSX、PPTX、Markdown、HTML、JSON 或 CSV。",
        ("file:read", "file:write"),
        _schema({"file_id": {"type": "string"}, "format": {"type": "string"}}, ["file_id", "format"]),
        _schema({"filename": {"type": "string"}, "media_type": {"type": "string"}, "size": {"type": "integer"}}),
    ),
    "file.summarize": BuiltinTool(
        "file.summarize",
        "文件摘要",
        "file",
        "基于提取文本生成短摘要。",
        ("file:read",),
        _schema({"file_id": {"type": "string"}, "max_chars": {"type": "integer"}}),
        _schema({"summary": {"type": "string"}}),
    ),
    "file.embed": BuiltinTool(
        "file.embed",
        "文件向量化",
        "file",
        "生成本地确定性向量表示，便于演示知识库索引流程。",
        ("file:read",),
        _schema({"file_id": {"type": "string"}}, ["file_id"]),
        _schema({"embedding": {"type": "array"}}),
    ),
    "file.read": BuiltinTool(
        "file.read",
        "读取工作区文件",
        "filesystem",
        "读取后端工作区中被授权的项目文件或上传文件。",
        ("file:read",),
        _schema({"path": {"type": "string"}, "file_id": {"type": "string"}}),
        _schema({"content": {"type": "string"}}),
    ),
    "file.write": BuiltinTool(
        "file.write",
        "写入工作区文件",
        "filesystem",
        "在受控工作区写入 AI 构建工具或项目快照文件。",
        ("file:write",),
        _schema({"path": {"type": "string"}, "content": {"type": "string"}}),
        _schema({"path": {"type": "string"}, "size": {"type": "integer"}}),
    ),
    "artifact.create_pdf": BuiltinTool(
        "artifact.create_pdf",
        "生成 PDF",
        "artifact",
        "生成真实 PDF 文件并创建聊天产物卡片。",
        ("artifact:create", "artifact:export"),
        _schema({"conversation_id": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, ["conversation_id"]),
        _schema({"artifact": {"type": "object"}, "export_url": {"type": "string"}}),
    ),
    "artifact.create_docx": BuiltinTool(
        "artifact.create_docx",
        "生成 Word",
        "artifact",
        "生成 DOCX 产物并提供预览与导出。",
        ("artifact:create",),
        _schema({"conversation_id": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, ["conversation_id"]),
        _schema({"artifact": {"type": "object"}}),
    ),
    "artifact.create_xlsx": BuiltinTool(
        "artifact.create_xlsx",
        "生成 Excel",
        "artifact",
        "生成 XLSX 表格产物并提供预览与导出。",
        ("artifact:create",),
        _schema({"conversation_id": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, ["conversation_id"]),
        _schema({"artifact": {"type": "object"}}),
    ),
    "artifact.create_pptx": BuiltinTool(
        "artifact.create_pptx",
        "生成 PPT",
        "artifact",
        "生成 PPTX 演示产物并提供预览与导出。",
        ("artifact:create",),
        _schema({"conversation_id": {"type": "string"}, "title": {"type": "string"}, "body": {"type": "string"}}, ["conversation_id"]),
        _schema({"artifact": {"type": "object"}}),
    ),
    "artifact.create_html": BuiltinTool(
        "artifact.create_html",
        "生成 HTML",
        "artifact",
        "创建 HTML/Web 产物。",
        ("artifact:create",),
        _schema({"conversation_id": {"type": "string"}, "title": {"type": "string"}, "html": {"type": "string"}}, ["conversation_id"]),
        _schema({"artifact": {"type": "object"}}),
    ),
    "artifact.create_web_app": BuiltinTool(
        "artifact.create_web_app",
        "生成 Web App",
        "artifact",
        "创建可预览、编辑、Diff、部署的 Web 应用产物。",
        ("artifact:create",),
        _schema({"conversation_id": {"type": "string"}, "title": {"type": "string"}, "html": {"type": "string"}}, ["conversation_id"]),
        _schema({"artifact": {"type": "object"}}),
    ),
    "artifact.export": BuiltinTool(
        "artifact.export",
        "导出产物",
        "artifact",
        "返回产物导出地址和默认格式。",
        ("artifact:export",),
        _schema({"artifact_id": {"type": "string"}, "format": {"type": "string"}}, ["artifact_id"]),
        _schema({"export_url": {"type": "string"}}),
    ),
    "artifact.preview": BuiltinTool(
        "artifact.preview",
        "预览产物",
        "artifact",
        "返回产物预览地址。",
        ("artifact:read",),
        _schema({"artifact_id": {"type": "string"}}, ["artifact_id"]),
        _schema({"preview_url": {"type": "string"}}),
    ),
    "artifact.revise": BuiltinTool(
        "artifact.revise",
        "修订产物",
        "artifact",
        "更新产物文件并产生新版本。",
        ("artifact:update",),
        _schema({"artifact_id": {"type": "string"}, "files": {"type": "object"}, "summary": {"type": "string"}}, ["artifact_id", "files"]),
        _schema({"artifact": {"type": "object"}}),
    ),
    "artifact.diff": BuiltinTool(
        "artifact.diff",
        "产物 Diff",
        "artifact",
        "计算当前产物与上一版本差异。",
        ("artifact:read",),
        _schema({"artifact_id": {"type": "string"}}, ["artifact_id"]),
        _schema({"diff": {"type": "object"}}),
    ),
    "sandbox.run": BuiltinTool(
        "sandbox.run",
        "沙箱运行",
        "runtime",
        "在受控沙箱中执行命令，默认返回安全模拟结果。",
        ("sandbox:run",),
        _schema({"command": {"type": "string"}, "sandbox_id": {"type": "string"}}),
        _schema({"stdout": {"type": "string"}, "exit_code": {"type": "integer"}}),
    ),
    "browser.preview": BuiltinTool(
        "browser.preview",
        "浏览器预览",
        "runtime",
        "为 Web 产物返回浏览器预览地址。",
        ("browser:preview",),
        _schema({"artifact_id": {"type": "string"}, "url": {"type": "string"}}),
        _schema({"preview_url": {"type": "string"}}),
    ),
    "db.inspect": BuiltinTool(
        "db.inspect",
        "数据库检查",
        "backend",
        "检查当前数据库表结构摘要。",
        ("db:inspect",),
        _schema({}),
        _schema({"tables": {"type": "array"}}),
    ),
    "api.test": BuiltinTool(
        "api.test",
        "API 测试",
        "backend",
        "执行 API 冒烟测试摘要。",
        ("api:test",),
        _schema({"path": {"type": "string"}}),
        _schema({"status": {"type": "string"}}),
    ),
    "test.run": BuiltinTool(
        "test.run",
        "运行测试",
        "qa",
        "记录测试运行请求并返回可审查日志。",
        ("test:run",),
        _schema({"command": {"type": "string"}}),
        _schema({"status": {"type": "string"}, "log": {"type": "string"}}),
    ),
    "security.audit": BuiltinTool(
        "security.audit",
        "安全审计",
        "qa",
        "对操作、产物或配置执行基础风险审计。",
        ("security:audit",),
        _schema({"target": {"type": "string"}}),
        _schema({"risk_score": {"type": "number"}, "findings": {"type": "array"}}),
    ),
    "document.review": BuiltinTool(
        "document.review",
        "文档审查",
        "qa",
        "审查文档结构、遗漏和交付风险。",
        ("document:review",),
        _schema({"text": {"type": "string"}}),
        _schema({"findings": {"type": "array"}}),
    ),
    "deploy.preview": BuiltinTool(
        "deploy.preview",
        "预览部署",
        "deploy",
        "为产物创建预览部署记录。",
        ("deploy:preview",),
        _schema({"artifact_id": {"type": "string"}}, ["artifact_id"]),
        _schema({"deployment": {"type": "object"}}),
    ),
    "deploy.rollback": BuiltinTool(
        "deploy.rollback",
        "部署回滚",
        "deploy",
        "创建回滚记录并返回当前可用预览地址。",
        ("deploy:rollback",),
        _schema({"deployment_id": {"type": "string"}}, ["deployment_id"]),
        _schema({"status": {"type": "string"}}),
    ),
}


TOOLBOXES = {
    "master": [
        "file.extract_text",
        "file.summarize",
        "file.embed",
        "artifact.preview",
        "artifact.export",
        "db.inspect",
        "api.test",
        "security.audit",
    ],
    "frontend": ["file.read", "file.write", "artifact.create_web_app", "sandbox.run", "browser.preview"],
    "backend": ["file.read", "file.write", "db.inspect", "sandbox.run", "api.test"],
    "reviewer": ["artifact.diff", "test.run", "security.audit", "document.review"],
    "deploy": ["artifact.export", "deploy.preview", "deploy.rollback", "sandbox.run"],
    "writing": [
        "file.extract_text",
        "file.summarize",
        "artifact.create_pdf",
        "artifact.create_docx",
        "artifact.create_pptx",
        "document.review",
    ],
    "chat": ["file.extract_text", "file.preview", "file.summarize"],
}


def ensure_tool_tables(db: Session) -> None:
    ToolDefinition.__table__.create(bind=db.get_bind(), checkfirst=True)


def builtin_tool_dicts() -> list[dict[str, Any]]:
    return [tool.to_dict() for tool in BUILTIN_TOOLS.values()]


def get_official_toolbox(agent_type: str) -> list[str]:
    return TOOLBOXES.get(agent_type, TOOLBOXES["chat"])


def normalize_tool_names(values: list[Any]) -> list[str]:
    names = []
    aliases = {
        "file_read": "file.read",
        "file_write": "file.write",
        "code_execute": "sandbox.run",
        "sandbox_run": "sandbox.run",
        "knowledge_retrieve": "file.summarize",
        "deploy": "deploy.preview",
        "mcp": "mcp.invoke",
        "skills": "skill.run",
    }
    for item in values:
        name = str(item.get("name") if isinstance(item, dict) else item).strip()
        if not name:
            continue
        names.append(aliases.get(name, name))
    return list(dict.fromkeys(names))


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


def _visible_tool_query(user: User, workspace_id: str | None = None):
    query = select(ToolDefinition).where(ToolDefinition.deleted_at.is_(None))
    if user.role != "admin":
        query = query.where((ToolDefinition.owner_id == user.id) | (ToolDefinition.owner_id.is_(None)))
    if workspace_id:
        query = query.where((ToolDefinition.workspace_id == workspace_id) | (ToolDefinition.workspace_id.is_(None)))
    return query


def list_tools(db: Session, user: User, *, workspace_id: str | None = None, q: str | None = None) -> list[dict[str, Any]]:
    ensure_tool_tables(db)
    items = builtin_tool_dicts()
    custom = [tool_definition_to_dict(item) for item in db.scalars(_visible_tool_query(user, workspace_id)).all()]
    items.extend(custom)
    if q:
        needle = q.lower()
        items = [
            item
            for item in items
            if needle in item["name"].lower()
            or needle in item.get("display_name", "").lower()
            or needle in item.get("description", "").lower()
            or needle in item.get("category", "").lower()
        ]
    items.sort(key=lambda item: (item.get("category", ""), item.get("name", "")))
    return items


def get_custom_tool(db: Session, user: User, tool_id_or_name: str) -> ToolDefinition:
    ensure_tool_tables(db)
    tool = db.scalar(
        _visible_tool_query(user).where(
            (ToolDefinition.id == tool_id_or_name) | (ToolDefinition.name == tool_id_or_name)
        )
    )
    if not tool:
        raise NotFoundError("工具不存在")
    return tool


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
        "artifact": artifact_to_dict(artifact),
        "preview_message_id": preview.id,
        "preview_url": f"/api/v1/artifacts/{artifact.id}/preview",
        "export_url": f"/api/v1/artifacts/{artifact.id}/export?format={export_format}",
        "format": export_format,
    }


def _run_custom_python(tool: ToolDefinition, arguments: dict[str, Any]) -> dict[str, Any]:
    code = str((tool.implementation or {}).get("code") or "").strip()
    if not code:
        return {"status": "noop", "result": arguments, "message": "工具暂无代码，已返回输入参数。"}
    if re.search(r"\b(import|open|exec|eval|compile|__|os\.|subprocess|socket|shutil)\b", code):
        raise ValidationAppError("自定义工具代码包含未授权的高风险能力，请改用 sandbox.run 或 MCP 工具。")
    safe_builtins = {
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "enumerate": enumerate,
        "range": range,
    }
    namespace: dict[str, Any] = {"arguments": arguments, "result": None, "json": json}
    exec(code, {"__builtins__": safe_builtins}, namespace)
    return {"status": "succeeded", "result": namespace.get("result")}


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
        return {"status": "succeeded", "path": arguments.get("path") or "/api/v1/health", "result": "health route reachable in current app"}
    if name in {"sandbox.run", "test.run"}:
        command = str(arguments.get("command") or "echo AgentHub")
        return {"status": "succeeded", "command": command, "exit_code": 0, "stdout": f"[mock-sandbox] {command}", "stderr": ""}
    if name == "browser.preview":
        artifact_id = str(arguments.get("artifact_id") or "")
        url = str(arguments.get("url") or (f"/api/v1/artifacts/{artifact_id}/preview" if artifact_id else "about:blank"))
        return {"status": "succeeded", "preview_url": url}
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


def invoke_tool(db: Session, user: User, tool_id_or_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    ensure_tool_tables(db)
    name = tool_id_or_name
    if name in BUILTIN_TOOLS:
        return {"tool": BUILTIN_TOOLS[name].to_dict(), "result": invoke_builtin_tool(db, user, name, arguments)}
    tool = get_custom_tool(db, user, tool_id_or_name)
    if tool.status != "active":
        raise ValidationAppError("工具未启用")
    result = _run_custom_python(tool, arguments)
    tool.extra = {**(tool.extra or {}), "last_invocation_at": utcnow().isoformat().replace("+00:00", "Z")}
    db.commit()
    return {"tool": tool_definition_to_dict(tool), "result": result}
