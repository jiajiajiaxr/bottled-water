"""
[LEGACY] 智能体运行时工具链。

包含 Agent 工具选择、执行和单轮 tool loop 实现。

.. note::
    `build_tools_for_agent` 和 `execute_tool_by_name` 仍被新旧编排器共用，
    继续保留。
    `run_agentic_tool_loop` 及辅助函数（select_* / execute_*）
    已被 `agent_runtime` 运行时替代，仅用于兼容旧编排器 workflow 模式。
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent, Conversation, McpServer, Skill, User
from app.events import app_event_bus as event_bus
from app.services.mcp_runtime import invoke_mcp_tool_recorded, tool_name
from app.services.tool_registry import BUILTIN_TOOLS, invoke_tool, normalize_tool_names
from app.services.model_config_resolver import create_provider_from_db


TOOL_INTENT_PATTERN = re.compile(
    r"(skill|mcp|工具|调用|读取|文件|沙箱|命令|运行|检索|搜索|部署|分析|生成|代码|测试)",
    re.I,
)


def _workspace_id(conversation: Conversation) -> str | None:
    extra = conversation.extra or {}
    value = extra.get("workspace_id") or extra.get("workspaceId")
    return str(value) if value else None


def _score_text(prompt: str, *values: Any) -> int:
    haystack = " ".join(str(value or "") for value in values).lower()
    tokens = [token for token in re.split(r"[\s,，。:：/\\|_-]+", prompt.lower()) if len(token) >= 2]
    score = 0
    for token in tokens:
        if token in haystack:
            score += 2 if len(token) > 3 else 1
    return score


def _skill_tool_refs(skill: Skill) -> list[dict[str, Any]]:
    return [item for item in (skill.tools or []) if isinstance(item, dict)]


def _mcp_tool_args(prompt: str, name: str) -> dict[str, Any]:
    args: dict[str, Any] = {"input": prompt, "prompt": prompt}
    if name.startswith("file.") or "read" in name:
        args.setdefault("path", ".")
    if "sandbox" in name or "run" in name:
        args.setdefault("command", "echo AgentHub MCP sandbox smoke")
    if "search" in name or "retrieve" in name:
        args.setdefault("query", prompt)
    return args


async def select_skills(db: AsyncSession, conversation: Conversation, prompt: str, limit: int = 2) -> list[Skill]:
    workspace_id = _workspace_id(conversation)
    query = select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
    query = query.where(or_(Skill.owner_id == conversation.creator_id, Skill.owner_id.is_(None)))
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    else:
        query = query.where(Skill.workspace_id.is_(None))
    scored: list[tuple[int, Skill]] = []
    for skill in (await db.scalars(query)).all():
        score = _score_text(prompt, skill.name, skill.description, skill.category, skill.tags, skill.content)
        if score > 0 or (TOOL_INTENT_PATTERN.search(prompt) and skill.source in {"ai", "mcp"}):
            scored.append((score + (2 if skill.source in {"ai", "mcp"} else 0), skill))
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    return [skill for score, skill in scored if score > 0][:limit]


async def select_agent_skills(db: AsyncSession, conversation: Conversation, prompt: str, agent: Agent, limit: int = 2) -> list[Skill]:
    config = agent.config or {}
    allowed_ids = [str(item) for item in config.get("skill_ids") or [] if item]
    if not allowed_ids:
        return []
    workspace_id = _workspace_id(conversation)
    query = select(Skill).where(Skill.id.in_(allowed_ids), Skill.deleted_at.is_(None), Skill.status == "active")
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    skills = (await db.scalars(query)).all()
    scored = [(_score_text(prompt, skill.name, skill.description, skill.category, skill.tags, skill.content), skill) for skill in skills]
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    ordered = [skill for _score, skill in scored]
    return ordered[:limit]


async def select_mcp_action(db: AsyncSession, conversation: Conversation, prompt: str) -> tuple[McpServer, str] | None:
    if not TOOL_INTENT_PATTERN.search(prompt):
        return None
    workspace_id = _workspace_id(conversation)
    query = select(McpServer).where(
        McpServer.deleted_at.is_(None),
        McpServer.enabled.is_(True),
        or_(McpServer.owner_id == conversation.creator_id, McpServer.owner_id.is_(None)),
    )
    if workspace_id:
        query = query.where(or_(McpServer.workspace_id == workspace_id, McpServer.workspace_id.is_(None)))
    servers = (await db.scalars(query)).all()
    best: tuple[int, McpServer, str] | None = None
    for server in servers:
        tools = [item for item in (server.tools or []) if isinstance(item, dict) and item.get("enabled", True)]
        if not tools:
            tools = [{"name": item, "description": "Allowed by tool_filter", "enabled": True} for item in (server.tool_filter or [])]
        for tool in tools:
            name = tool_name(tool)
            if not name:
                continue
            score = _score_text(prompt, server.name, name, tool.get("description"), server.tool_filter)
            if "mcp" in prompt.lower() or "工具" in prompt:
                score += 2
            if best is None or score > best[0]:
                best = (score, server, name)
    if not best or best[0] <= 0:
        return None
    return best[1], best[2]


async def select_agent_mcp_action(db: AsyncSession, conversation: Conversation, prompt: str, agent: Agent) -> tuple[McpServer, str] | None:
    config = agent.config or {}
    allowed_ids = [str(item) for item in config.get("mcp_server_ids") or [] if item]
    if not allowed_ids or not TOOL_INTENT_PATTERN.search(prompt):
        return None
    workspace_id = _workspace_id(conversation)
    query = select(McpServer).where(
        McpServer.id.in_(allowed_ids),
        McpServer.deleted_at.is_(None),
        McpServer.enabled.is_(True),
    )
    if workspace_id:
        query = query.where(or_(McpServer.workspace_id == workspace_id, McpServer.workspace_id.is_(None)))
    best: tuple[int, McpServer, str] | None = None
    for server in (await db.scalars(query)).all():
        tools = [item for item in (server.tools or []) if isinstance(item, dict) and item.get("enabled", True)]
        if not tools:
            tools = [{"name": item, "description": "Allowed by tool_filter", "enabled": True} for item in (server.tool_filter or [])]
        for tool in tools:
            name = tool_name(tool)
            score = _score_text(prompt, server.name, name, tool.get("description"), server.tool_filter)
            if best is None or score > best[0]:
                best = (score, server, name)
    return (best[1], best[2]) if best and best[0] > 0 else None


def _builtin_tool_args(conversation: Conversation, prompt: str, name: str) -> dict[str, Any]:
    args: dict[str, Any] = {"input": prompt, "prompt": prompt, "conversation_id": conversation.id}
    if name.startswith("artifact.create_"):
        args.update({"title": "AgentHub 工具产物", "body": prompt})
        if name in {"artifact.create_html", "artifact.create_web_app"}:
            args["html"] = ""
    if name == "db.inspect":
        return {}
    if name in {"api.test", "test.run"}:
        args.setdefault("path", "/api/v1/health")
        args.setdefault("command", "pytest -q")
    if name == "sandbox.run":
        args.setdefault("command", "echo AgentHub worker sandbox")
    if name == "security.audit":
        args.setdefault("target", prompt)
    if name == "document.review":
        args.setdefault("text", prompt)
    return args


def _select_agent_builtin_tools(agent: Agent, prompt: str, limit: int) -> list[str]:
    names = normalize_tool_names((agent.config or {}).get("tools") or [])
    allowed = [name for name in names if name in BUILTIN_TOOLS]
    if not allowed:
        return []
    prompt_lower = prompt.lower()
    preferred: list[str] = []
    artifact_map = [
        ("pdf", "artifact.create_pdf"),
        ("word", "artifact.create_docx"),
        ("docx", "artifact.create_docx"),
        ("excel", "artifact.create_xlsx"),
        ("xlsx", "artifact.create_xlsx"),
        ("ppt", "artifact.create_pptx"),
        ("pptx", "artifact.create_pptx"),
        ("html", "artifact.create_html"),
        ("web", "artifact.create_web_app"),
        ("网页", "artifact.create_web_app"),
        ("页面", "artifact.create_web_app"),
    ]
    for keyword, tool in artifact_map:
        if keyword in prompt_lower and tool in allowed:
            preferred.append(tool)
    if re.search(r"(文件|附件|摘要|读取|解析)", prompt, re.I):
        preferred.extend([name for name in ("file.extract_text", "file.summarize", "file.preview") if name in allowed])
    if re.search(r"(测试|api|接口)", prompt, re.I):
        preferred.extend([name for name in ("api.test", "test.run") if name in allowed])
    if re.search(r"(数据库|db|schema|表)", prompt, re.I) and "db.inspect" in allowed:
        preferred.append("db.inspect")
    if re.search(r"(命令|运行|沙箱|代码)", prompt, re.I) and "sandbox.run" in allowed:
        preferred.append("sandbox.run")
    if re.search(r"(审查|安全|风险|合规)", prompt, re.I):
        preferred.extend([name for name in ("security.audit", "document.review") if name in allowed])
    if not preferred and TOOL_INTENT_PATTERN.search(prompt):
        preferred = allowed[:1]
    return list(dict.fromkeys(preferred))[:limit]


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
                arguments=_mcp_tool_args(prompt, str(ref["name"])),
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
        arguments=_mcp_tool_args(prompt, name),
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
        payload = await invoke_tool(db, user, name, _builtin_tool_args(conversation, prompt, name))
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
        for name in _select_agent_builtin_tools(agent, prompt, max_steps - len(results)):
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
    from app.services.tool_registry import BUILTIN_TOOLS

    tools: list[dict[str, Any]] = []
    config = agent.config or {}

    # 内置工具
    allowed_tool_names = normalize_tool_names(config.get("tools") or [])
    for name in allowed_tool_names:
        if name not in BUILTIN_TOOLS:
            continue
        builtin = BUILTIN_TOOLS[name]
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
    from app.services.tool_registry import BUILTIN_TOOLS, invoke_builtin_tool

    # 内置工具
    if tool_name in BUILTIN_TOOLS:
        return await invoke_builtin_tool(db, user, tool_name, {**arguments, "conversation_id": conversation.id})

    # Skill
    if tool_name.startswith("skill."):
        skill_id = tool_name.removeprefix("skill.")
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
            server = await db.get(McpServer, server_id)
            if not server or server.deleted_at is not None or not server.enabled:
                return {"type": "mcp", "server_id": server_id, "tool_name": actual_tool_name, "status": "failed", "output": "MCP server 不存在或未启用"}
            return await execute_mcp_action(db, server=server, name=actual_tool_name, user=user, conversation=conversation, prompt=arguments.get("prompt", ""))

    return {"type": "unknown", "tool_name": tool_name, "status": "failed", "output": f"未知工具: {tool_name}"}
