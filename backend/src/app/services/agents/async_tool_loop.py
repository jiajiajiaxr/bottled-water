"""AsyncSession-backed Agent tool loop adapter.

The synchronous Function Calling path lives in ``app.services.agents.tool_loop``.
This module keeps the V2 ``agent_runtime`` adapter working with ``AsyncSession``
without putting business logic back into the deprecated
``app.services.agentic_runtime`` compatibility shim.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent, Conversation, McpServer, Skill, ToolDefinition, User
from app.events import app_event_bus as event_bus
from app.services.agents.async_tool_selection import (
    builtin_tool_args,
    mcp_tool_args,
    select_agent_builtin_tools,
    select_agent_mcp_action,
    select_agent_skills,
    select_mcp_action,
    select_skills,
)
from app.services.mcp_runtime import invoke_mcp_tool_recorded, tool_name
from app.services.model_config_resolver import create_provider_from_db
from app.services.tools.builtins.registry import BUILTIN_TOOLS
from app.services.tools.catalog import sync_builtin_tool_definitions
from app.services.tools.executor import invoke_tool as invoke_tool_sync
from app.services.tools.permissions import normalize_tool_names


def _is_async_session(db: Any) -> bool:
    return isinstance(db, AsyncSession)


async def _invoke_catalog_tool(
    db: AsyncSession,
    user: User,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if _is_async_session(db):
        return await db.run_sync(
            lambda session: invoke_tool_sync(session, user, tool_name, arguments)
        )
    return invoke_tool_sync(db, user, tool_name, arguments)


def _skill_tool_refs(skill: Skill) -> list[dict[str, Any]]:
    return [item for item in (skill.tools or []) if isinstance(item, dict)]


async def execute_skill(
    db: AsyncSession,
    *,
    skill: Skill,
    user: User | None,
    conversation: Conversation,
    prompt: str,
) -> dict[str, Any]:
    channel = f"conversation:{conversation.id}"
    await event_bus.publish(channel, "tool:started", {"type": "skill", "skill_id": skill.id, "name": skill.name})
    mcp_refs = [item for item in _skill_tool_refs(skill) if item.get("type") == "mcp" and item.get("server_id") and item.get("name")]
    if mcp_refs:
        ref = mcp_refs[0]
        server = await db.get(McpServer, str(ref["server_id"]))
        if server:
            invocation = await invoke_mcp_tool_recorded(
                db,
                server=server,
                tool_name_value=str(ref["name"]),
                arguments=mcp_tool_args(prompt, str(ref["name"])),
                user=user,
                conversation_id=conversation.id,
                timeout_ms=min(server.timeout_ms or 30000, 5000),
            )
            result = {
                "type": "skill_mcp",
                "skill_id": skill.id,
                "skill_name": skill.name,
                "status": invocation["status"],
                "output": invocation.get("result") or invocation.get("error_message"),
                "invocation_id": invocation["id"],
            }
            await event_bus.publish(channel, "tool:finished", result)
            return result

    system_prompt = skill.prompt or skill.content or f"You are the AgentHub skill {skill.name}."
    try:
        provider = await create_provider_from_db(db)
        if not provider:
            raise RuntimeError("无可用模型配置")
        response = await provider.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps({"input": prompt, "skill": skill.name}, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=600,
        )
        output = response.content
        model_name = response.model or "unknown"
        status = "succeeded"
    except Exception as exc:
        output = f"[skill-fallback] {skill.name}: {prompt[:180]}"
        model_name = "mock-skill-execution"
        status = f"fallback:{exc.__class__.__name__}"
    result = {"type": "skill", "skill_id": skill.id, "skill_name": skill.name, "status": status, "output": output, "model": model_name}
    await event_bus.publish(channel, "tool:finished", result)
    return result


async def execute_mcp_action(
    db: AsyncSession,
    *,
    server: McpServer,
    name: str,
    user: User | None,
    conversation: Conversation,
    prompt: str,
) -> dict[str, Any]:
    channel = f"conversation:{conversation.id}"
    await event_bus.publish(channel, "tool:started", {"type": "mcp", "server_id": server.id, "tool_name": name})
    invocation = await invoke_mcp_tool_recorded(
        db,
        server=server,
        tool_name_value=name,
        arguments=mcp_tool_args(prompt, name),
        user=user,
        conversation_id=conversation.id,
        timeout_ms=min(server.timeout_ms or 30000, 5000),
    )
    result = {
        "type": "mcp",
        "server_id": server.id,
        "server_name": server.name,
        "tool_name": name,
        "status": invocation["status"],
        "output": invocation.get("result") or invocation.get("error_message"),
        "invocation_id": invocation["id"],
    }
    await event_bus.publish(channel, "tool:finished", result)
    return result


async def execute_builtin_tool_action(
    db: AsyncSession,
    *,
    agent: Agent,
    user: User | None,
    conversation: Conversation,
    name: str,
    prompt: str,
) -> dict[str, Any]:
    channel = f"conversation:{conversation.id}"
    await event_bus.publish(channel, "tool:started", {"type": "tool", "agent_id": agent.id, "tool_name": name})
    if not user:
        user = await db.get(User, conversation.creator_id)
    try:
        payload = await _invoke_catalog_tool(
            db,
            user,
            name,
            builtin_tool_args(conversation, prompt, name),
        )
        result = {
            "type": "tool",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "tool_name": name,
            "status": payload.get("result", {}).get("status", "succeeded"),
            "output": payload.get("result"),
        }
    except Exception as exc:
        result = {
            "type": "tool",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "tool_name": name,
            "status": f"failed:{exc.__class__.__name__}",
            "output": str(exc)[:500],
        }
    await event_bus.publish(channel, "tool:finished", result)
    return result


async def run_agentic_tool_loop(
    db: AsyncSession,
    conversation: Conversation,
    prompt: str,
    *,
    max_steps: int = 2,
    agent: Agent | None = None,
) -> dict[str, Any]:
    """
    .. deprecated::
        该函数已被 `agent_runtime` 运行时替代。
        仅保留用于兼容旧编排器的 workflow 模式。
        新代码请使用 `agent_runtime.Session` + `OrchestratorV2`。
    """
    user = await db.get(User, conversation.creator_id)
    if agent:
        loop_cfg = (agent.config or {}).get("agentic_loop") or {}
        allowed_tools = normalize_tool_names((agent.config or {}).get("tools") or [])
        allowed_skill_ids = (agent.config or {}).get("skill_ids") or []
        allowed_mcp_ids = (agent.config or {}).get("mcp_server_ids") or []
        loop_enabled = bool(loop_cfg.get("enabled")) and bool(allowed_tools or allowed_skill_ids or allowed_mcp_ids)
        if not loop_enabled:
            return {
                "mode": "chat_only",
                "agent_id": agent.id,
                "agent_name": agent.name,
                "max_steps": 0,
                "selected_skill_count": 0,
                "executions": [],
                "summary": "Agent 未授权工具/Skill/MCP，小循环未启动。",
            }
        max_steps = min(int(loop_cfg.get("max_steps") or max_steps or 2), 4)

    selected_skills = (
        await select_agent_skills(db, conversation, prompt, agent, limit=max_steps)
        if agent
        else await select_skills(db, conversation, prompt, limit=max_steps)
    )
    results: list[dict[str, Any]] = []
    for skill in selected_skills:
        if len(results) >= max_steps:
            break
        results.append(await execute_skill(db, skill=skill, user=user, conversation=conversation, prompt=prompt))
        await db.commit()

    if agent and len(results) < max_steps:
        for name in select_agent_builtin_tools(agent, prompt, max_steps - len(results)):
            results.append(await execute_builtin_tool_action(db, agent=agent, user=user, conversation=conversation, name=name, prompt=prompt))
            await db.commit()
            if len(results) >= max_steps:
                break

    if len(results) < max_steps:
        action = await select_agent_mcp_action(db, conversation, prompt, agent) if agent else await select_mcp_action(db, conversation, prompt)
        if action:
            server, name = action
            results.append(await execute_mcp_action(db, server=server, name=name, user=user, conversation=conversation, prompt=prompt))
            await db.commit()

    return {
        "mode": "agent_short_loop" if agent else "short_agentic_loop",
        **({"agent_id": agent.id, "agent_name": agent.name} if agent else {}),
        "max_steps": max_steps,
        "selected_skill_count": len(selected_skills),
        "executions": results,
        "summary": "\n".join(
            f"- {item.get('type')} {item.get('skill_name') or item.get('tool_name')}: {item.get('status')}"
            for item in results
        ),
    }


async def build_tools_for_agent(db: AsyncSession, agent: Agent) -> list[dict[str, Any]]:
    """将 Agent 配置的 tools/skills/mcp 转为 OpenAI Function Calling 格式。"""

    tools: list[dict[str, Any]] = []
    config = agent.config or {}

    # Tool 目录：内置和自定义工具都优先从数据库 ToolDefinition 读取。
    allowed_tool_names = normalize_tool_names(config.get("tools") or [])
    tool_rows: list[ToolDefinition] = []
    if allowed_tool_names and _is_async_session(db):
        try:
            await db.run_sync(sync_builtin_tool_definitions)
            tool_query = select(ToolDefinition).where(
                ToolDefinition.deleted_at.is_(None),
                ToolDefinition.status == "active",
                (ToolDefinition.name.in_(allowed_tool_names))
                | (ToolDefinition.id.in_(allowed_tool_names)),
            )
            tool_rows = [
                item
                for item in (await db.scalars(tool_query)).all()
                if isinstance(item, ToolDefinition)
            ]
        except Exception:
            tool_rows = []
    seen_tool_names: set[str] = set()
    for tool in tool_rows:
        if tool.name in seen_tool_names:
            continue
        seen_tool_names.add(tool.name)
        tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or tool.display_name or tool.name,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        })
    for name in allowed_tool_names:
        if name in seen_tool_names:
            continue
        builtin = BUILTIN_TOOLS.get(name)
        if not builtin:
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": builtin.description,
                "parameters": builtin.input_schema,
            },
        })

    # Skill（作为 function 暴露）
    allowed_skill_ids = [str(item) for item in config.get("skill_ids") or [] if item]
    if allowed_skill_ids:
        skill_query = select(Skill).where(
            Skill.id.in_(allowed_skill_ids),
            Skill.deleted_at.is_(None),
            Skill.status == "active",
        )
        for skill in (await db.scalars(skill_query)).all():
            tools.append({
                "type": "function",
                "function": {
                    "name": f"skill.{skill.id}",
                    "description": skill.description or skill.prompt or f"Skill: {skill.name}",
                    "parameters": {
                        "type": "object",
                        "properties": {"prompt": {"type": "string", "description": "用户请求内容"}},
                        "required": ["prompt"],
                    },
                },
            })

    # MCP 工具
    allowed_mcp_ids = [str(item) for item in config.get("mcp_server_ids") or [] if item]
    if allowed_mcp_ids:
        mcp_query = select(McpServer).where(
            McpServer.id.in_(allowed_mcp_ids),
            McpServer.deleted_at.is_(None),
            McpServer.enabled.is_(True),
        )
        for server in (await db.scalars(mcp_query)).all():
            server_tools = [item for item in (server.tools or []) if isinstance(item, dict) and item.get("enabled", True)]
            if not server_tools:
                server_tools = [{"name": item, "description": "Allowed by tool_filter", "enabled": True} for item in (server.tool_filter or [])]
            for t in server_tools:
                name = tool_name(t)
                if not name:
                    continue
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp.{server.id}.{name}",
                        "description": t.get("description") or f"MCP tool {name} on {server.name}",
                        "parameters": t.get("inputSchema") or t.get("input_schema") or {"type": "object", "properties": {}},
                    },
                })

    return tools


async def execute_tool_by_name(
    db: AsyncSession,
    *,
    agent: Agent,
    user: User | None,
    conversation: Conversation,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """根据 tool_name 路由到内置工具/Skill/MCP 执行器。"""

    # 内置工具
    if tool_name in BUILTIN_TOOLS:
        if tool_name not in normalize_tool_names((agent.config or {}).get("tools") or []):
            return _unauthorized_tool_result(tool_name)
        if not user:
            user = await db.get(User, conversation.creator_id)
        payload = await _invoke_catalog_tool(
            db,
            user,
            tool_name,
            {**arguments, "conversation_id": conversation.id},
        )
        result = payload.get("result") or {}
        return {
            "type": "tool",
            "tool_name": tool_name,
            "status": result.get("status", "succeeded"),
            "output": result,
            "invocation_id": payload.get("invocation_id"),
        }

    # Skill
    if tool_name.startswith("skill."):
        skill_id = tool_name.removeprefix("skill.")
        if skill_id not in {str(item) for item in (agent.config or {}).get("skill_ids") or [] if item}:
            return _unauthorized_tool_result(tool_name, result_type="skill", extra={"skill_id": skill_id})
        skill = await db.get(Skill, skill_id)
        if not skill or skill.deleted_at is not None or skill.status != "active":
            return {"type": "skill", "skill_id": skill_id, "status": "failed", "output": "Skill 不存在或未启用"}
        return await execute_skill(db, skill=skill, user=user, conversation=conversation, prompt=arguments.get("prompt", ""))

    # MCP
    if tool_name.startswith("mcp."):
        parts = tool_name.split(".")
        if len(parts) >= 3:
            server_id = parts[1]
            actual_tool_name = ".".join(parts[2:])
            if server_id not in {str(item) for item in (agent.config or {}).get("mcp_server_ids") or [] if item}:
                return _unauthorized_tool_result(
                    tool_name,
                    result_type="mcp",
                    extra={"server_id": server_id, "tool_name": actual_tool_name},
                )
            server = await db.get(McpServer, server_id)
            if not server or server.deleted_at is not None or not server.enabled:
                return {"type": "mcp", "server_id": server_id, "tool_name": actual_tool_name, "status": "failed", "output": "MCP server 不存在或未启用"}
            return await execute_mcp_action(db, server=server, name=actual_tool_name, user=user, conversation=conversation, prompt=arguments.get("prompt", ""))

    authorized_tool = await _resolve_authorized_db_tool(db, agent, tool_name)
    if authorized_tool:
        if not user:
            user = await db.get(User, conversation.creator_id)
        payload = await _invoke_catalog_tool(
            db,
            user,
            authorized_tool.name,
            {**arguments, "conversation_id": conversation.id},
        )
        result = payload.get("result") or {}
        return {
            "type": "tool",
            "tool_name": authorized_tool.name,
            "status": result.get("status", "succeeded"),
            "output": result,
            "invocation_id": payload.get("invocation_id"),
        }

    if await _db_tool_exists(db, tool_name):
        return _unauthorized_tool_result(tool_name)

    return {"type": "unknown", "tool_name": tool_name, "status": "failed", "output": f"未知工具: {tool_name}"}


def _unauthorized_tool_result(
    tool_name: str,
    *,
    result_type: str = "tool",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": result_type,
        "tool_name": tool_name,
        "status": "failed",
        "output": f"Agent 未授权调用工具: {tool_name}",
        **(extra or {}),
    }


async def _resolve_authorized_db_tool(
    db: AsyncSession,
    agent: Agent,
    tool_name: str,
) -> ToolDefinition | None:
    allowed_tool_names = normalize_tool_names((agent.config or {}).get("tools") or [])
    if not allowed_tool_names or not _is_async_session(db):
        return None
    tool = await db.scalar(
        select(ToolDefinition).where(
            ToolDefinition.deleted_at.is_(None),
            ToolDefinition.status == "active",
            (ToolDefinition.name == tool_name) | (ToolDefinition.id == tool_name),
            (ToolDefinition.name.in_(allowed_tool_names))
            | (ToolDefinition.id.in_(allowed_tool_names)),
        )
    )
    if not tool or tool.is_builtin or tool.type == "builtin":
        return None
    return tool


async def _db_tool_exists(db: AsyncSession, tool_name: str) -> bool:
    if not _is_async_session(db):
        return False
    value = await db.scalar(
        select(ToolDefinition.id).where(
            ToolDefinition.deleted_at.is_(None),
            ToolDefinition.status == "active",
            (ToolDefinition.name == tool_name) | (ToolDefinition.id == tool_name),
        )
    )
    return isinstance(value, str) and bool(value)
