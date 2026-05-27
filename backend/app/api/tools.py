from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import ToolDefinition, User, Workspace, utcnow
from app.schemas.requests import CreateToolRequest, GenerateToolRequest, InvokeToolRequest, UpdateToolRequest
from app.services.ark import ark_client
from app.services.serialization import redact_sensitive, tool_definition_to_dict
from app.services.tools.builtins.registry import BUILTIN_TOOLS
from app.services.tools.catalog import ensure_tool_tables, get_tool_definition, list_tools
from app.services.tools.executor import invoke_tool_async


router = APIRouter(tags=["tools"])


def _validate_workspace(db: Session, user: User, workspace_id: str | None) -> None:
    if not workspace_id:
        return
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("工作区不存在")
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该工作区")


def _owned_tool(db: Session, user: User, tool_id: str) -> ToolDefinition:
    ensure_tool_tables(db)
    tool = db.scalar(select(ToolDefinition).where(ToolDefinition.id == tool_id, ToolDefinition.deleted_at.is_(None)))
    if not tool:
        raise NotFoundError("工具不存在")
    if tool.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只能修改自己创建的工具")
    return tool


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip().lower()).strip("._")
    return name or "generated_tool"


def _tool_workspace_file(name: str, code: str) -> str:
    root = Path(__file__).resolve().parents[3] / "var" / "ai-tools" / "generated"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{_safe_name(name)}.py"
    path.write_text(code, encoding="utf-8")
    return str(path)


def _fallback_tool_spec(payload: GenerateToolRequest, reason: str) -> dict[str, Any]:
    name = payload.name or _safe_name(payload.intent[:60])
    code = (
        "text = str(arguments.get('input') or arguments.get('text') or arguments)\n"
        "result = {\n"
        "    'summary': text[:500],\n"
        "    'note': 'AI 生成工具的安全占位实现，可继续编辑代码。'\n"
        "}\n"
    )
    return {
        "name": _safe_name(name),
        "display_name": payload.name or "AI 生成工具",
        "description": payload.intent,
        "category": payload.category,
        "type": "custom_python",
        "input_schema": {"type": "object", "additionalProperties": True},
        "output_schema": {"type": "object", "additionalProperties": True},
        "permissions": payload.allowed_permissions,
        "implementation": {"language": "python", "code": code},
        "runtime": {"mode": "restricted_python", "workspace": "var/ai-tools"},
        "tags": list(dict.fromkeys([*payload.tags, "ai-generated"])),
        "config": {"generation": {"provider_status": "fallback", "reason": reason}},
    }


async def _generate_tool_spec(payload: GenerateToolRequest) -> dict[str, Any]:
    fallback = _fallback_tool_spec(payload, "not_called")
    try:
        result = await ark_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 AgentHub 的工具构建助手。只返回 JSON。字段包含 name, display_name, "
                        "description, category, type, input_schema, output_schema, permissions, "
                        "implementation, runtime, tags, config。implementation.code 必须是受限 Python "
                        "片段：读取 arguments 字典，最后把输出写入 result 变量；不要 import，不要读写系统文件，"
                        "不要访问网络，不要包含密钥。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "name": payload.name,
                            "intent": payload.intent,
                            "requirements": payload.requirements,
                            "category": payload.category,
                            "allowed_permissions": payload.allowed_permissions,
                            "tags": payload.tags,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1400,
            purpose="tool_generation",
        )
        data = _parse_json_object(result.text)
        if not data:
            spec = _fallback_tool_spec(payload, "non_json_adapter_response")
            spec["config"]["generation"].update({"model": result.model, "raw_text_preview": result.text[:300]})
            return spec
        implementation = data.get("implementation") if isinstance(data.get("implementation"), dict) else fallback["implementation"]
        config = data.get("config") if isinstance(data.get("config"), dict) else {}
        config = {
            **config,
            "generation": {
                **(config.get("generation") if isinstance(config.get("generation"), dict) else {}),
                "provider_status": getattr(result, "provider_status", "ok"),
                "model": result.model,
                "usage": result.usage,
            },
        }
        return {
            "name": _safe_name(str(data.get("name") or fallback["name"])),
            "display_name": str(data.get("display_name") or payload.name or fallback["display_name"])[:200],
            "description": str(data.get("description") or fallback["description"]),
            "category": str(data.get("category") or payload.category),
            "type": str(data.get("type") or "custom_python"),
            "input_schema": data.get("input_schema") if isinstance(data.get("input_schema"), dict) else fallback["input_schema"],
            "output_schema": data.get("output_schema") if isinstance(data.get("output_schema"), dict) else fallback["output_schema"],
            "permissions": data.get("permissions") if isinstance(data.get("permissions"), list) else payload.allowed_permissions,
            "implementation": implementation,
            "runtime": data.get("runtime") if isinstance(data.get("runtime"), dict) else fallback["runtime"],
            "tags": list(dict.fromkeys([*payload.tags, *(data.get("tags") if isinstance(data.get("tags"), list) else []), "ai-generated"])),
            "config": config,
        }
    except Exception as exc:
        spec = _fallback_tool_spec(payload, f"adapter_error:{exc.__class__.__name__}")
        spec["config"]["generation"]["error"] = str(exc)[:300]
        return spec


@router.get("/tools")
async def list_tool_catalog(
    workspace_id: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_workspace(db, user, workspace_id)
    items = list_tools(db, user, workspace_id=workspace_id, q=q)
    return ok({"items": items, "total": len(items)})


@router.post("/tools")
async def create_tool(
    payload: CreateToolRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_tool_tables(db)
    _validate_workspace(db, user, payload.workspace_id)
    if payload.name in BUILTIN_TOOLS:
        raise ValidationAppError("不能覆盖平台内置工具")
    duplicate = db.scalar(
        select(ToolDefinition).where(
            ToolDefinition.owner_id == user.id,
            ToolDefinition.workspace_id == payload.workspace_id,
            ToolDefinition.name == payload.name,
            ToolDefinition.deleted_at.is_(None),
        )
    )
    if duplicate:
        raise ValidationAppError("工具名称已存在")
    implementation = redact_sensitive(payload.implementation)
    code = str(implementation.get("code") or "")
    source_path = _tool_workspace_file(payload.name, code) if code else None
    tool = ToolDefinition(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        name=_safe_name(payload.name),
        display_name=payload.display_name or payload.name,
        description=payload.description,
        category=payload.category,
        type=payload.type,
        status=payload.status,
        version=payload.version,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        permissions=payload.permissions,
        implementation={**implementation, **({"source_path": source_path} if source_path else {})},
        runtime=payload.runtime or {"mode": "restricted_python", "workspace": "var/ai-tools"},
        tags=payload.tags,
        config=redact_sensitive(payload.config),
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return ok(tool_definition_to_dict(tool), "工具已创建")


@router.post("/tools/generate")
async def generate_tool(
    payload: GenerateToolRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_tool_tables(db)
    _validate_workspace(db, user, payload.workspace_id)
    spec = await _generate_tool_spec(payload)
    if spec["name"] in BUILTIN_TOOLS:
        spec["name"] = f"custom_{spec['name']}"
    code = str((spec.get("implementation") or {}).get("code") or "")
    source_path = _tool_workspace_file(spec["name"], code) if code else None
    tool = ToolDefinition(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        name=spec["name"],
        display_name=spec["display_name"],
        description=spec["description"],
        category=spec["category"],
        type=spec["type"],
        status="active",
        version="1.0.0",
        input_schema=spec["input_schema"],
        output_schema=spec["output_schema"],
        permissions=spec["permissions"],
        implementation=redact_sensitive({**spec["implementation"], **({"source_path": source_path} if source_path else {})}),
        runtime=redact_sensitive(spec["runtime"]),
        tags=spec["tags"],
        config=redact_sensitive(spec["config"]),
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return ok(tool_definition_to_dict(tool), "AI 已生成工具")


@router.get("/tools/{tool_id}")
async def get_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(tool_definition_to_dict(get_tool_definition(db, user, tool_id)))


@router.patch("/tools/{tool_id}")
async def update_tool(
    tool_id: str,
    payload: UpdateToolRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool = _owned_tool(db, user, tool_id)
    data = payload.model_dump(exclude_unset=True)
    if "workspace_id" in data:
        _validate_workspace(db, user, data["workspace_id"])
    if "implementation" in data and data["implementation"]:
        code = str(data["implementation"].get("code") or "")
        if code:
            data["implementation"] = {**data["implementation"], "source_path": _tool_workspace_file(tool.name, code)}
    for key, value in data.items():
        if key in {"implementation", "runtime", "config"} and value is not None:
            value = redact_sensitive(value)
        setattr(tool, key, value)
    db.commit()
    db.refresh(tool)
    return ok(tool_definition_to_dict(tool), "工具已更新")


@router.delete("/tools/{tool_id}")
async def delete_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool = _owned_tool(db, user, tool_id)
    tool.deleted_at = utcnow()
    tool.status = "deleted"
    db.commit()
    return ok({"id": tool.id, "deleted": True})


@router.post("/tools/{tool_id}/invoke")
async def invoke_tool_endpoint(
    tool_id: str,
    payload: InvokeToolRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_workspace(db, user, payload.workspace_id)
    result = await invoke_tool_async(db, user, tool_id, payload.arguments)
    return ok(result, "工具调用完成")
