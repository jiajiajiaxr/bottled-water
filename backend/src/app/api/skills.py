"""
Skills API

Skill CRUD 和 AI 生成，统一使用 model_provider 调用 LLM。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import McpServer, Skill, User, Workspace, utcnow
from app.schemas.common import ApiResponse, SkillOut
from app.schemas.requests import (
    CreateSkillRequest, GenerateSkillRequest, ImportMcpSkillRequest, TestSkillRequest, UpdateSkillRequest,
)
from app.services.serialization import redact_sensitive, skill_to_dict
from model_provider import create_provider
from model_provider.core.config import ModelConfig
from app.core.config import get_settings

router = APIRouter(tags=["skills"])


def _model_provider():
    settings = get_settings()
    api_key = getattr(settings, "ARK_API_KEY", "")
    model = getattr(settings, "ARK_DEFAULT_MODEL", "ep-xxx")
    if not api_key:
        return None
    return create_provider(ModelConfig(provider="ark", model=model, api_key=api_key))


async def ensure_skill_tables(db: AsyncSession) -> None:
    await db.run_sync(lambda session: Skill.__table__.create(bind=session.get_bind(), checkfirst=True))


def _visible_skill_filter(user: User):
    if user.role == "admin":
        return true()
    return (Skill.owner_id == user.id) | (Skill.owner_id.is_(None))


async def _validate_workspace(db: AsyncSession, user: User, workspace_id: str | None) -> None:
    if not workspace_id:
        return
    workspace = await db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("Workspace not found")
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("No permission for this workspace")


async def _get_skill(db: AsyncSession, user: User, skill_id: str) -> Skill:
    await ensure_skill_tables(db)
    skill = await db.scalar(select(Skill).where(Skill.id == skill_id, Skill.deleted_at.is_(None)))
    if not skill:
        raise NotFoundError("Skill not found")
    if skill.owner_id not in {None, user.id} and user.role != "admin":
        raise ForbiddenError("No permission for this skill")
    return skill


async def _get_mcp_server(db: AsyncSession, user: User, server_id: str) -> McpServer:
    server = await db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.deleted_at.is_(None)))
    if not server:
        raise NotFoundError("MCP server not found")
    if server.owner_id not in {None, user.id} and user.role != "admin":
        raise ForbiddenError("No permission for this MCP server")
    return server


def _tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("name") or tool.get("id") or "").strip()


def _select_mcp_tools(server: McpServer, tool_names: list[str]) -> list[dict[str, Any]]:
    tools = [item for item in (server.tools or []) if isinstance(item, dict)]
    if not tools and server.tool_filter:
        tools = [{"name": item, "description": f"Allowed: {item}", "enabled": True} for item in server.tool_filter]
    if tool_names:
        wanted = set(tool_names)
        tools = [item for item in tools if _tool_name(item) in wanted]
    tools = [item for item in tools if _tool_name(item)]
    if not tools:
        raise ValidationAppError("No MCP tools available. Probe the server first or pass tool_filter.")
    return tools


def _mcp_tool_ref(server: McpServer, tool: dict) -> dict:
    ref = {"type": "mcp", "server_id": server.id, "server_name": server.name, "name": _tool_name(tool), "description": tool.get("description") or "", "enabled": tool.get("enabled", True)}
    for key in ("input_schema", "inputSchema", "parameters"):
        if isinstance(tool.get(key), dict):
            ref["input_schema"] = tool[key]
            break
    return redact_sensitive(ref)


def _skill_content_for_tools(server: McpServer, tools: list[dict]) -> str:
    lines = [f"Use MCP server `{server.name}` with selected tools:"]
    for tool in tools:
        lines.append(f"- {_tool_name(tool)}: {tool.get('description') or 'No description'}")
    lines.append("Report tool errors clearly.")
    return "\n".join(lines)


def _fallback_skill_spec(payload: GenerateSkillRequest, reason: str) -> dict:
    name = payload.name or payload.intent.strip().splitlines()[0][:60] or "Generated Skill"
    return {
        "name": name, "description": payload.intent,
        "category": payload.category,
        "content": f"Goal: {payload.intent}\nRequirements: {payload.requirements or 'None'}",
        "prompt": "You are an AgentHub skill. Return concise, verifiable output.",
        "input_schema": {"type": "object", "properties": {"input": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
        "tags": list(dict.fromkeys([*payload.tags, "ai-generated"])),
        "tools": [],
        "config": {"generation": {"status": "mock_fallback", "reason": reason}},
    }


def _parse_json_object(text: str) -> dict | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


async def _generate_skill_spec(payload: GenerateSkillRequest) -> dict:
    provider = _model_provider()
    if not provider:
        return _fallback_skill_spec(payload, "no_api_key")

    try:
        result = await provider.chat(
            messages=[
                {"role": "system", "content": "Return only JSON for an AgentHub skill: name, description, category, content, prompt, input_schema, output_schema, tags, tools, config."},
                {"role": "user", "content": json.dumps({"name": payload.name, "intent": payload.intent, "requirements": payload.requirements, "category": payload.category, "tags": payload.tags}, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        data = _parse_json_object(result.content)
        if not data:
            spec = _fallback_skill_spec(payload, "non_json_response")
            spec["config"]["generation"]["model_preview"] = result.content[:300]
            return spec
    except Exception as exc:
        spec = _fallback_skill_spec(payload, f"error:{exc.__class__.__name__}")
        spec["config"]["generation"]["error"] = str(exc)[:300]
        return spec

    fallback = _fallback_skill_spec(payload, "missing_fields")
    config = data.get("config") or {}
    config = {**(payload.config or {}), **config, "generation": {"status": "ok", "model": result.model or "unknown"}}
    return {
        "name": str(data.get("name") or fallback["name"])[:160],
        "description": str(data.get("description") or fallback["description"]),
        "category": str(data.get("category") or payload.category),
        "content": str(data.get("content") or data.get("instructions") or fallback["content"]),
        "prompt": str(data.get("prompt") or fallback["prompt"]),
        "input_schema": data.get("input_schema") if isinstance(data.get("input_schema"), dict) else fallback["input_schema"],
        "output_schema": data.get("output_schema") if isinstance(data.get("output_schema"), dict) else fallback["output_schema"],
        "tags": list(dict.fromkeys([*payload.tags, "ai-generated"])),
        "tools": data.get("tools") if isinstance(data.get("tools"), list) else [],
        "config": config,
    }


@router.get("/skills", response_model=ApiResponse[dict])
async def list_skills(workspace_id: str | None = None, status: str | None = None, source: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_skill_tables(db)
    await _validate_workspace(db, user, workspace_id)
    query = select(Skill).where(Skill.deleted_at.is_(None)).where(_visible_skill_filter(user))
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    if status:
        query = query.where(Skill.status == status)
    if source:
        query = query.where(Skill.source == source)
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(Skill.name.ilike(pattern), Skill.description.ilike(pattern)))
    skills = (await db.scalars(query.order_by(Skill.updated_at.desc()))).all()
    return ok({"items": [skill_to_dict(it) for it in skills], "total": len(skills)})


@router.post("/skills", response_model=ApiResponse[SkillOut])
async def create_skill(payload: CreateSkillRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_skill_tables(db)
    await _validate_workspace(db, user, payload.workspace_id)
    skill = Skill(
        owner_id=user.id, workspace_id=payload.workspace_id, name=payload.name,
        description=payload.description, category=payload.category, source=payload.source,
        status=payload.status, version=payload.version, content=payload.content, prompt=payload.prompt,
        input_schema=payload.input_schema, output_schema=payload.output_schema,
        tools=redact_sensitive(payload.tools), tags=payload.tags, config=redact_sensitive(payload.config),
    )
    await db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill created")


@router.post("/skills/import-mcp", response_model=ApiResponse[SkillOut])
@router.post("/skills/import-mcp-tools", response_model=ApiResponse[SkillOut])
async def import_mcp_skill(payload: ImportMcpSkillRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_skill_tables(db)
    server = await _get_mcp_server(db, user, payload.mcp_server_id)
    workspace_id = payload.workspace_id or server.workspace_id
    await _validate_workspace(db, user, workspace_id)
    tools = _select_mcp_tools(server, payload.tool_names)
    tool_refs = [_mcp_tool_ref(server, item) for item in tools]
    skill = Skill(
        owner_id=user.id, workspace_id=workspace_id, name=payload.name or f"{server.name} Skill",
        description=payload.description or f"Skill from MCP server {server.name} with {len(tool_refs)} tool(s).",
        category=payload.category, source="mcp", status="active", version="1.0.0",
        content=_skill_content_for_tools(server, tools),
        prompt="You are a tool-backed skill. Select from declared MCP tools, validate inputs, summarize result.",
        input_schema={"type": "object", "additionalProperties": True},
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
        tools=tool_refs, tags=list(dict.fromkeys([*payload.tags, "mcp", server.name])),
        config=redact_sensitive({**(payload.config or {}), "mcp": {"server_id": server.id, "server_name": server.name, "transport": server.transport, "tool_count": len(tool_refs)}}),
    )
    await db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill imported from MCP tools")


@router.post("/skills/generate", response_model=ApiResponse[SkillOut])
@router.post("/skills/ai-generate", response_model=ApiResponse[SkillOut])
async def generate_skill(payload: GenerateSkillRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_skill_tables(db)
    await _validate_workspace(db, user, payload.workspace_id)
    spec = await _generate_skill_spec(payload)
    skill = Skill(
        owner_id=user.id, workspace_id=payload.workspace_id, name=spec["name"], description=spec["description"],
        category=spec["category"], source="ai", status="active", version="1.0.0",
        content=spec["content"], prompt=spec["prompt"], input_schema=spec["input_schema"],
        output_schema=spec["output_schema"], tools=redact_sensitive(spec["tools"]),
        tags=spec["tags"], config=redact_sensitive(spec["config"]),
    )
    await db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill generated")


@router.get("/skills/{skill_id}", response_model=ApiResponse[SkillOut])
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(skill_to_dict(await _get_skill(db, user, skill_id)))


@router.patch("/skills/{skill_id}", response_model=ApiResponse[SkillOut])
async def update_skill(skill_id: str, payload: UpdateSkillRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    skill = await _get_skill(db, user, skill_id)
    if skill.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("Only the owner can modify this skill")
    data = payload.model_dump(exclude_unset=True)
    if "workspace_id" in data:
        await _validate_workspace(db, user, data["workspace_id"])
    for key, value in data.items():
        if key in {"tools", "config"} and value is not None:
            value = redact_sensitive(value)
        setattr(skill, key, value)
    await db.commit()
    await db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill updated")


@router.delete("/skills/{skill_id}", response_model=ApiResponse[dict])
async def delete_skill(skill_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    skill = await _get_skill(db, user, skill_id)
    if skill.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("Only the owner can modify this skill")
    skill.deleted_at = utcnow()
    skill.status = "deleted"
    await db.commit()
    return ok({"id": skill.id, "deleted": True})


@router.post("/skills/{skill_id}/test", response_model=ApiResponse[dict])
async def test_skill(skill_id: str, payload: TestSkillRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    skill = await _get_skill(db, user, skill_id)
    input_text = payload.message or (payload.input if isinstance(payload.input, str) else json.dumps(payload.input, ensure_ascii=False))
    system_prompt = skill.prompt or skill.content or f"You are the skill {skill.name}."
    provider = _model_provider()
    if not provider:
        response = f"[mock] {skill.name} received: {input_text[:160]}"
        return ok({"skill": skill_to_dict(skill), "status": "passed", "response": response, "model": "mock", "usage": {}}, "Skill test completed")

    try:
        result = await provider.chat(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": input_text}],
            temperature=0.2,
            max_tokens=800,
        )
        response = result.content
        model = result.model or "unknown"
        usage = result.usage or {}
        provider_status = "ok"
    except Exception as exc:
        response = f"[error] {exc}"
        model = "error"
        usage = {}
        provider_status = f"error:{exc.__class__.__name__}"

    skill.extra = {**(skill.extra or {}), "last_test": {"status": "passed", "input_preview": input_text[:160], "provider_status": provider_status, "model": model, "tested_at": utcnow().isoformat()}}
    await db.commit()
    await db.refresh(skill)
    return ok({"skill": skill_to_dict(skill), "status": "passed", "response": response, "model": model, "usage": usage, "provider_status": provider_status}, "Skill test completed")