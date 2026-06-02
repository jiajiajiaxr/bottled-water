from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import McpServer, Skill, User
from app.schemas.requests import (
    CreateSkillRequest,
    GenerateSkillRequest,
    ImportMcpSkillRequest,
    TestSkillRequest,
    UpdateSkillRequest,
)
from app.services.ark import ark_client
from app.services.serialization import redact_sensitive, skill_to_dict
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.catalog import (
    ensure_skill_owner,
    ensure_skill_tables,
    get_skill_for_user,
    validate_workspace,
    visible_skill_filter,
)
from app.services.skills.package import soft_delete_skill_package
from app.services.skills.testing import run_skill_test
from app.services.skills.versions import set_skill_manifest


router = APIRouter(tags=["skills"])


def _get_mcp_server(db: Session, user: User, server_id: str) -> McpServer:
    server = db.scalar(
        select(McpServer).where(McpServer.id == server_id, McpServer.deleted_at.is_(None))
    )
    if not server:
        raise NotFoundError("MCP server not found")
    if server.owner_id not in {None, user.id} and user.role != "admin":
        raise ForbiddenError("No permission for this MCP server")
    return server


def _tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("name") or tool.get("id") or tool.get("tool_name") or "").strip()


def _select_mcp_tools(server: McpServer, tool_names: list[str]) -> list[dict[str, Any]]:
    tools = [item for item in (server.tools or []) if isinstance(item, dict)]
    if not tools and server.tool_filter:
        tools = [
            {"name": item, "description": f"Allowed MCP tool pattern: {item}", "enabled": True}
            for item in server.tool_filter
        ]
    if tool_names:
        wanted = set(tool_names)
        tools = [item for item in tools if _tool_name(item) in wanted]
    tools = [item for item in tools if _tool_name(item)]
    if not tools:
        raise ValidationAppError("No MCP tools available. Probe the server first or pass tool_filter.")
    return tools


def _mcp_tool_ref(server: McpServer, tool: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "type": "mcp",
        "server_id": server.id,
        "server_name": server.name,
        "name": _tool_name(tool),
        "description": tool.get("description") or "",
        "enabled": tool.get("enabled", True),
    }
    for key in ("input_schema", "inputSchema", "parameters", "schema"):
        if isinstance(tool.get(key), dict):
            ref["input_schema"] = tool[key]
            break
    return redact_sensitive(ref)


def _skill_content_for_tools(server: McpServer, tools: list[dict[str, Any]]) -> str:
    lines = [
        f"Use the MCP server `{server.name}` to complete tasks with the selected tools.",
        "Available tools:",
    ]
    for tool in tools:
        name = _tool_name(tool)
        description = tool.get("description") or "No description provided."
        lines.append(f"- {name}: {description}")
    lines.append("Prefer the narrowest tool that can satisfy the request and report tool errors clearly.")
    return "\n".join(lines)


def _skill_input_text(payload: TestSkillRequest) -> str:
    if payload.message:
        return payload.message
    if isinstance(payload.input, str):
        return payload.input
    return json.dumps(payload.input, ensure_ascii=False)


def _fallback_skill_spec(payload: GenerateSkillRequest, reason: str) -> dict[str, Any]:
    base_name = payload.name or payload.intent.strip().splitlines()[0][:60] or "Generated Skill"
    return {
        "name": base_name,
        "description": payload.intent,
        "category": payload.category,
        "content": "\n".join(
            [
                f"Goal: {payload.intent}",
                f"Requirements: {payload.requirements or 'None'}",
                "Process: clarify the input, produce a structured result, and include validation notes.",
            ]
        ),
        "prompt": (
            "You are an AgentHub skill. Follow the user's goal, respect the provided "
            "requirements, and return concise, verifiable output."
        ),
        "input_schema": {"type": "object", "properties": {"input": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"result": {"type": "string"}}},
        "tags": list(dict.fromkeys([*payload.tags, "ai-generated"])),
        "tools": [],
        "config": {
            "generation": {
                "provider_status": "mock_fallback",
                "reason": reason,
            }
        },
    }


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def _generate_skill_spec(payload: GenerateSkillRequest) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "Return only a JSON object for an AgentHub skill with keys: name, "
                "description, category, content, prompt, input_schema, output_schema, "
                "tags, tools, config. Do not include secrets."
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
                    "tags": payload.tags,
                },
                ensure_ascii=False,
            ),
        },
    ]
    try:
        result = await ark_client.chat(
            messages, temperature=0.2, max_tokens=1200, purpose="skill_generation"
        )
    except Exception as exc:
        spec = _fallback_skill_spec(payload, f"adapter_error:{exc.__class__.__name__}")
        spec["config"]["generation"]["error"] = str(exc)[:300]
        return spec

    data = _parse_json_object(result.text)
    if data is None:
        spec = _fallback_skill_spec(payload, "non_json_adapter_response")
        spec["config"]["generation"].update(
            {"model": result.model, "raw_text_preview": result.text[:300]}
        )
        return spec

    fallback = _fallback_skill_spec(payload, "missing_ai_field")
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    config = {
        **payload.config,
        **config,
        "generation": {
            **(config.get("generation") if isinstance(config.get("generation"), dict) else {}),
            "provider_status": getattr(result, "provider_status", "ok"),
            "model": result.model,
            "usage": result.usage,
        },
    }
    return {
        "name": str(data.get("name") or fallback["name"])[:160],
        "description": str(data.get("description") or fallback["description"]),
        "category": str(data.get("category") or payload.category),
        "content": str(data.get("content") or data.get("instructions") or fallback["content"]),
        "prompt": str(data.get("prompt") or data.get("system_prompt") or fallback["prompt"]),
        "input_schema": data.get("input_schema")
        if isinstance(data.get("input_schema"), dict)
        else fallback["input_schema"],
        "output_schema": data.get("output_schema")
        if isinstance(data.get("output_schema"), dict)
        else fallback["output_schema"],
        "tags": list(
            dict.fromkeys(
                [
                    *payload.tags,
                    *(data.get("tags") if isinstance(data.get("tags"), list) else []),
                    "ai-generated",
                ]
            )
        ),
        "tools": data.get("tools") if isinstance(data.get("tools"), list) else [],
        "config": config,
    }


@router.get("/skills")
async def list_skills(
    workspace_id: str | None = None,
    status: str | None = None,
    source: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_skill_tables(db)
    validate_workspace(db, user, workspace_id)
    query = select(Skill).where(Skill.deleted_at.is_(None)).where(visible_skill_filter(user))
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    if status:
        query = query.where(Skill.status == status)
    if source:
        query = query.where(Skill.source == source)
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(Skill.name.ilike(pattern), Skill.description.ilike(pattern)))
    skills = db.scalars(query.order_by(Skill.updated_at.desc())).all()
    return ok({"items": [skill_to_dict(item) for item in skills], "total": len(skills)})


@router.post("/skills")
async def create_skill(
    payload: CreateSkillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_skill_tables(db)
    validate_workspace(db, user, payload.workspace_id)
    skill = Skill(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        source=payload.source,
        status=payload.status,
        version=payload.version,
        content=payload.content,
        prompt=payload.prompt,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        tools=redact_sensitive(payload.tools),
        tags=payload.tags,
        config=redact_sensitive(payload.config),
    )
    set_skill_manifest(skill, payload.manifest or legacy_skill_manifest(skill), user=user)
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill created")


@router.post("/skills/import-mcp")
@router.post("/skills/import-mcp-tools")
async def import_mcp_skill(
    payload: ImportMcpSkillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_skill_tables(db)
    server = _get_mcp_server(db, user, payload.mcp_server_id)
    workspace_id = payload.workspace_id or server.workspace_id
    validate_workspace(db, user, workspace_id)
    tools = _select_mcp_tools(server, payload.tool_names)
    tool_refs = [_mcp_tool_ref(server, item) for item in tools]
    name = payload.name or f"{server.name} Skill"
    skill = Skill(
        owner_id=user.id,
        workspace_id=workspace_id,
        name=name,
        description=payload.description
        or f"Skill generated from MCP server {server.name} with {len(tool_refs)} tool(s).",
        category=payload.category,
        source="mcp",
        status="active",
        version="1.0.0",
        content=_skill_content_for_tools(server, tools),
        prompt=(
            "You are a tool-backed skill. Select from the declared MCP tools, "
            "validate inputs, and summarize the result."
        ),
        input_schema={"type": "object", "additionalProperties": True},
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
        tools=tool_refs,
        tags=list(dict.fromkeys([*payload.tags, "mcp", server.name])),
        config=redact_sensitive(
            {
                **payload.config,
                "mcp": {
                    "server_id": server.id,
                    "server_name": server.name,
                    "transport": server.transport,
                    "tool_count": len(tool_refs),
                },
            }
        ),
    )
    set_skill_manifest(skill, legacy_skill_manifest(skill), user=user)
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill imported from MCP tools")


@router.post("/skills/generate")
@router.post("/skills/ai-generate")
async def generate_skill(
    payload: GenerateSkillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_skill_tables(db)
    validate_workspace(db, user, payload.workspace_id)
    spec = await _generate_skill_spec(payload)
    skill = Skill(
        owner_id=user.id,
        workspace_id=payload.workspace_id,
        name=spec["name"],
        description=spec["description"],
        category=spec["category"],
        source="ai",
        status="active",
        version="1.0.0",
        content=spec["content"],
        prompt=spec["prompt"],
        input_schema=spec["input_schema"],
        output_schema=spec["output_schema"],
        tools=redact_sensitive(spec["tools"]),
        tags=spec["tags"],
        config=redact_sensitive(spec["config"]),
    )
    set_skill_manifest(skill, spec.get("manifest") or legacy_skill_manifest(skill), user=user)
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill generated")


@router.get("/skills/{skill_id}")
async def get_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(skill_to_dict(get_skill_for_user(db, user, skill_id)))


@router.patch("/skills/{skill_id}")
async def update_skill(
    skill_id: str,
    payload: UpdateSkillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skill = get_skill_for_user(db, user, skill_id)
    ensure_skill_owner(skill, user)
    data = payload.model_dump(exclude_unset=True)
    manifest = data.pop("manifest", None)
    if "workspace_id" in data:
        validate_workspace(db, user, data["workspace_id"])
    for key, value in data.items():
        if key in {"tools", "config"} and value is not None:
            value = redact_sensitive(value)
        setattr(skill, key, value)
    if manifest is not None:
        set_skill_manifest(skill, manifest or legacy_skill_manifest(skill), user=user)
    db.commit()
    db.refresh(skill)
    return ok(skill_to_dict(skill), "Skill updated")


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skill = get_skill_for_user(db, user, skill_id)
    soft_delete_skill_package(db, skill, user)
    db.commit()
    return ok({"id": skill.id, "deleted": True})


@router.post("/skills/{skill_id}/test")
async def test_skill(
    skill_id: str,
    payload: TestSkillRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    skill = get_skill_for_user(db, user, skill_id)
    input_text = _skill_input_text(payload)
    report = await run_skill_test(
        db,
        skill=skill,
        user=user,
        payload={"prompt": input_text, "input": payload.input, "context": payload.context},
        context=payload.context,
    )
    runtime_result = report["result"]
    db.commit()
    db.refresh(skill)
    return ok(
        {
            "skill": skill_to_dict(skill),
            "status": report["status"],
            "response": runtime_result.get("output"),
            "model": runtime_result.get("model"),
            "usage": runtime_result.get("usage"),
            "provider_status": runtime_result.get("provider_status") or runtime_result.get("status"),
            "run_id": runtime_result.get("run_id"),
        },
        "Skill test completed",
    )
