from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Agent, Conversation, McpServer, Skill, ToolDefinition, User
from app.services.realtime.event_bus import event_bus
from app.services.agents.capability_permissions import (
    agent_uses_default_full_permissions,
    configured_mcp_server_ids,
    configured_skill_ids,
    configured_tool_names,
)
from app.services.mcp import invoke_mcp_tool_recorded, tool_name
from app.services.skills.runtime import SkillRuntime
from app.services.tools.builtins.registry import BUILTIN_TOOLS
from app.services.tools.executor import invoke_tool, invoke_tool_async


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


def _mcp_tool_args(prompt: str, name: str) -> dict[str, Any]:
    args: dict[str, Any] = {"input": prompt, "prompt": prompt}
    if name.startswith("file.") or "read" in name:
        args.setdefault("path", ".")
    if "sandbox" in name or "run" in name:
        args.setdefault("command", "echo AgentHub MCP sandbox smoke")
    if "search" in name or "retrieve" in name:
        args.setdefault("query", prompt)
    return args


def select_skills(db: Session, conversation: Conversation, prompt: str, limit: int = 2) -> list[Skill]:
    workspace_id = _workspace_id(conversation)
    query = select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
    query = query.where(or_(Skill.owner_id == conversation.creator_id, Skill.owner_id.is_(None)))
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    else:
        query = query.where(Skill.workspace_id.is_(None))
    scored: list[tuple[int, Skill]] = []
    for skill in db.scalars(query).all():
        score = _score_text(prompt, skill.name, skill.description, skill.category, skill.tags, skill.content)
        if score > 0 or (TOOL_INTENT_PATTERN.search(prompt) and skill.source in {"ai", "mcp"}):
            scored.append((score + (2 if skill.source in {"ai", "mcp"} else 0), skill))
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    return [skill for score, skill in scored if score > 0][:limit]


def select_agent_skills(db: Session, conversation: Conversation, prompt: str, agent: Agent, limit: int = 2) -> list[Skill]:
    default_all = agent_uses_default_full_permissions(agent)
    allowed_ids = configured_skill_ids(agent)
    if not allowed_ids and not default_all:
        return []
    workspace_id = _workspace_id(conversation)
    query = select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
    if allowed_ids and not default_all:
        query = query.where(Skill.id.in_(allowed_ids))
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    skills = db.scalars(query).all()
    scored = [(_score_text(prompt, skill.name, skill.description, skill.category, skill.tags, skill.content), skill) for skill in skills]
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    ordered = [skill for _score, skill in scored]
    return ordered[:limit]


def select_mcp_action(db: Session, conversation: Conversation, prompt: str) -> tuple[McpServer, str] | None:
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
    servers = db.scalars(query).all()
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


def select_agent_mcp_action(db: Session, conversation: Conversation, prompt: str, agent: Agent) -> tuple[McpServer, str] | None:
    default_all = agent_uses_default_full_permissions(agent)
    allowed_ids = configured_mcp_server_ids(agent)
    if (not allowed_ids and not default_all) or not TOOL_INTENT_PATTERN.search(prompt):
        return None
    workspace_id = _workspace_id(conversation)
    query = select(McpServer).where(
        McpServer.deleted_at.is_(None),
        McpServer.enabled.is_(True),
    )
    if allowed_ids and not default_all:
        query = query.where(McpServer.id.in_(allowed_ids))
    if workspace_id:
        query = query.where(or_(McpServer.workspace_id == workspace_id, McpServer.workspace_id.is_(None)))
    best: tuple[int, McpServer, str] | None = None
    for server in db.scalars(query).all():
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
    workspace_id = _workspace_id(conversation)
    if workspace_id:
        args["workspace_id"] = workspace_id
    if name.startswith("artifact.create_"):
        template = _document_template_for_prompt(prompt)
        args.update({"title": _document_title_for_prompt(prompt), "body": prompt, "template": template})
        if name in {"artifact.create_pdf", "artifact.create_docx"}:
            args["content_model"] = {
                "title": args["title"],
                "template": template,
                "cover": {"issuer": "AgentHub", "confidentiality": "演示文档"},
                "toc": {"enabled": True, "title": "目录"},
                "sections": [
                    {
                        "title": "需求概述",
                        "blocks": [
                            {"type": "callout", "title": "用户需求", "text": prompt},
                            {"type": "paragraph", "text": "以下内容基于当前对话需求生成，下载文件为真实二进制文档。"},
                        ],
                    },
                    {
                        "title": "正文内容",
                        "blocks": [
                            {"type": "paragraph", "text": prompt},
                            {"type": "list", "ordered": True, "items": ["背景说明", "方案要点", "交付建议"]},
                        ],
                    },
                ],
            }
        if name in {"artifact.create_html", "artifact.create_web_app"}:
            args["html"] = ""
    if name == "db.inspect":
        return {}
    if name in {"api.test", "test.run"}:
        args.setdefault("path", "/api/v1/health")
        args.setdefault("command", "pytest -q")
    if name == "sandbox.run":
        args.setdefault("command", "python --version")
    if name == "security.audit":
        args.setdefault("target", prompt)
    if name == "document.review":
        args.setdefault("text", prompt)
    return args


def _document_template_for_prompt(prompt: str) -> str:
    if re.search(r"(实验|lab|lab report)", prompt, re.I):
        return "lab_report"
    if re.search(r"(prd|需求文档|产品需求)", prompt, re.I):
        return "prd"
    if re.search(r"(会议|纪要|meeting)", prompt, re.I):
        return "meeting"
    if re.search(r"(方案|proposal|计划书|项目)", prompt, re.I):
        return "proposal"
    return "report"


def _document_title_for_prompt(prompt: str) -> str:
    if re.search(r"(pdf|word|docx|文档|报告|方案|prd|纪要|实验)", prompt, re.I):
        cleaned = re.sub(r"(生成|创建|写一份|一个|一份|pdf|word|docx|文档)", "", prompt, flags=re.I).strip(" ：:，,。")
        return (cleaned[:40] or "AgentHub 正式文档").strip()
    return "AgentHub 正式文档"


def _select_agent_builtin_tools(agent: Agent, prompt: str, limit: int) -> list[str]:
    names = _allowed_tool_names(agent)
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
    db: Session,
    *,
    skill: Skill,
    user: User | None,
    conversation: Conversation,
    prompt: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    channel = f"conversation:{conversation.id}"
    await event_bus.publish(channel, "tool:started", {"type": "skill", "skill_id": skill.id, "name": skill.name})
    result = await SkillRuntime().run(
        db,
        skill=skill,
        user=user,
        conversation=conversation,
        payload=payload or {"prompt": prompt, "input": prompt, "skill": skill.name},
    )
    await event_bus.publish(channel, "tool:finished", result)
    return result


async def execute_mcp_action(
    db: Session,
    *,
    server: McpServer,
    name: str,
    user: User | None,
    conversation: Conversation,
    prompt: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    channel = f"conversation:{conversation.id}"
    await event_bus.publish(channel, "tool:started", {"type": "mcp", "server_id": server.id, "tool_name": name})
    invocation = await invoke_mcp_tool_recorded(
        db,
        server=server,
        tool_name_value=name,
        arguments=arguments or _mcp_tool_args(prompt, name),
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
    db: Session,
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
        user = db.get(User, conversation.creator_id)
    try:
        payload = invoke_tool(db, user, name, _builtin_tool_args(conversation, prompt, name))
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
    db: Session,
    conversation: Conversation,
    prompt: str,
    *,
    max_steps: int = 2,
    agent: Agent | None = None,
) -> dict[str, Any]:
    user = db.get(User, conversation.creator_id)
    if agent:
        loop_cfg = (agent.config or {}).get("agentic_loop") or {}
        default_all = agent_uses_default_full_permissions(agent)
        allowed_tools = _allowed_tool_names(agent)
        allowed_skill_ids = configured_skill_ids(agent)
        allowed_mcp_ids = configured_mcp_server_ids(agent)
        loop_enabled = bool(loop_cfg.get("enabled")) and bool(default_all or allowed_tools or allowed_skill_ids or allowed_mcp_ids)
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
        select_agent_skills(db, conversation, prompt, agent, limit=max_steps)
        if agent
        else select_skills(db, conversation, prompt, limit=max_steps)
    )
    results: list[dict[str, Any]] = []
    for skill in selected_skills:
        if len(results) >= max_steps:
            break
        results.append(await execute_skill(db, skill=skill, user=user, conversation=conversation, prompt=prompt))
        db.commit()

    if agent and len(results) < max_steps:
        for name in _select_agent_builtin_tools(agent, prompt, max_steps - len(results)):
            results.append(await execute_builtin_tool_action(db, agent=agent, user=user, conversation=conversation, name=name, prompt=prompt))
            db.commit()
            if len(results) >= max_steps:
                break

    if len(results) < max_steps:
        action = select_agent_mcp_action(db, conversation, prompt, agent) if agent else select_mcp_action(db, conversation, prompt)
        if action:
            server, name = action
            results.append(await execute_mcp_action(db, server=server, name=name, user=user, conversation=conversation, prompt=prompt))
            db.commit()

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


def build_tools_for_agent(db: Session, agent: Agent) -> list[dict[str, Any]]:
    """将 Agent 配置的 tools/skills/mcp 转为 OpenAI Function Calling 格式。"""
    from app.services.skills.adapters.legacy import legacy_skill_manifest
    from app.services.tools.catalog import sync_builtin_tool_definitions

    tools: list[dict[str, Any]] = []
    default_all = agent_uses_default_full_permissions(agent)

    # Tool 目录（内置工具和自定义工具都从数据库目录读取元数据）
    allowed_tool_names = _allowed_tool_names(agent)
    if allowed_tool_names or default_all:
        tool_rows: list[ToolDefinition] = []
        try:
            sync_builtin_tool_definitions(db)
            tool_query = select(ToolDefinition).where(
                ToolDefinition.deleted_at.is_(None),
                ToolDefinition.status == "active",
            )
            if allowed_tool_names and not default_all:
                tool_query = tool_query.where(
                    (ToolDefinition.name.in_(allowed_tool_names)) | (ToolDefinition.id.in_(allowed_tool_names))
                )
            tool_rows = [item for item in db.scalars(tool_query).all() if isinstance(item, ToolDefinition)]
        except Exception:
            tool_rows = []
        for tool in tool_rows:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or tool.display_name or tool.name,
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            })
        if not tool_rows:
            for name in allowed_tool_names:
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
    allowed_skill_ids = configured_skill_ids(agent)
    if allowed_skill_ids or default_all:
        skill_query = select(Skill).where(
            Skill.deleted_at.is_(None),
            Skill.status == "active",
        )
        if allowed_skill_ids and not default_all:
            skill_query = skill_query.where(Skill.id.in_(allowed_skill_ids))
        for skill in db.scalars(skill_query).all():
            manifest = legacy_skill_manifest(skill)
            tools.append({
                "type": "function",
                "function": {
                    "name": f"skill.{skill.id}",
                    "description": manifest.get("description") or skill.description or f"Skill: {skill.name}",
                    "parameters": manifest.get("input_schema") or {
                        "type": "object",
                        "properties": {"prompt": {"type": "string", "description": "用户请求内容"}},
                        "required": ["prompt"],
                    },
                },
            })

    # MCP 工具
    allowed_mcp_ids = configured_mcp_server_ids(agent)
    if allowed_mcp_ids or default_all:
        mcp_query = select(McpServer).where(
            McpServer.deleted_at.is_(None),
            McpServer.enabled.is_(True),
        )
        if allowed_mcp_ids and not default_all:
            mcp_query = mcp_query.where(McpServer.id.in_(allowed_mcp_ids))
        for server in db.scalars(mcp_query).all():
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
    db: Session,
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
        if not _is_configured_tool(db, agent, tool_name):
            return _unauthorized_tool_result(tool_name)
        if not user:
            user = db.get(User, conversation.creator_id)
        payload = invoke_tool(db, user, tool_name, {**arguments, "conversation_id": conversation.id})
        return {
            "type": "tool",
            "tool_name": tool_name,
            "status": payload.get("result", {}).get("status", "succeeded"),
            "output": payload.get("result"),
            "invocation_id": payload.get("invocation_id"),
        }

    # Skill
    if tool_name.startswith("skill."):
        skill_id = tool_name.removeprefix("skill.")
        if not _is_configured_skill(agent, skill_id):
            return _unauthorized_tool_result(
                tool_name,
                result_type="skill",
                extra={"skill_id": skill_id},
            )
        skill = db.get(Skill, skill_id)
        if not skill or skill.deleted_at is not None or skill.status != "active":
            return {"type": "skill", "skill_id": skill_id, "status": "failed", "output": "Skill 不存在或未启用"}
        prompt = arguments.get("prompt") or arguments.get("input") or ""
        return await execute_skill(
            db,
            skill=skill,
            user=user,
            conversation=conversation,
            prompt=str(prompt),
            payload=arguments,
        )

    # MCP
    if tool_name.startswith("mcp."):
        parts = tool_name.split(".")
        if len(parts) >= 3:
            server_id = parts[1]
            actual_tool_name = ".".join(parts[2:])
            if not _is_configured_mcp(agent, server_id):
                return _unauthorized_tool_result(
                    tool_name,
                    result_type="mcp",
                    extra={"server_id": server_id, "tool_name": actual_tool_name},
                )
            server = db.get(McpServer, server_id)
            if not server or server.deleted_at is not None or not server.enabled:
                return {"type": "mcp", "server_id": server_id, "tool_name": actual_tool_name, "status": "failed", "output": "MCP server 不存在或未启用"}
            return await execute_mcp_action(
                db,
                server=server,
                name=actual_tool_name,
                user=user,
                conversation=conversation,
                prompt=arguments.get("prompt", ""),
                arguments=arguments,
            )

    authorized_tool = _resolve_authorized_db_tool(db, agent, tool_name)
    if authorized_tool:
        if not user:
            user = db.get(User, conversation.creator_id)
        payload = await invoke_tool_async(db, user, authorized_tool.name, {**arguments, "conversation_id": conversation.id})
        result = payload.get("result") or {}
        return {
            "type": "tool",
            "tool_name": authorized_tool.name,
            "status": result.get("status", "succeeded"),
            "output": result,
            "invocation_id": payload.get("invocation_id"),
        }

    if _db_tool_exists(db, tool_name):
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


def _is_configured_tool(db: Session, agent: Agent, tool_name: str) -> bool:
    if agent_uses_default_full_permissions(agent):
        return tool_name in BUILTIN_TOOLS or _db_tool_exists(db, tool_name)
    allowed = _allowed_tool_names(agent)
    if tool_name in allowed:
        return True
    if not allowed:
        return False
    return db.scalar(
        select(ToolDefinition.id).where(
            ToolDefinition.deleted_at.is_(None),
            ToolDefinition.status == "active",
            ToolDefinition.name == tool_name,
            ToolDefinition.id.in_(allowed),
        )
    ) is not None


def _is_configured_skill(agent: Agent, skill_id: str) -> bool:
    return agent_uses_default_full_permissions(agent) or skill_id in set(configured_skill_ids(agent))


def _is_configured_mcp(agent: Agent, server_id: str) -> bool:
    return agent_uses_default_full_permissions(agent) or server_id in set(configured_mcp_server_ids(agent))


def _resolve_authorized_db_tool(db: Session, agent: Agent, tool_name: str) -> ToolDefinition | None:
    allowed_tool_names = _allowed_tool_names(agent)
    default_all = agent_uses_default_full_permissions(agent)
    if not allowed_tool_names and not default_all:
        return None
    query = select(ToolDefinition).where(
        ToolDefinition.deleted_at.is_(None),
        ToolDefinition.status == "active",
        (ToolDefinition.name == tool_name) | (ToolDefinition.id == tool_name),
    )
    if allowed_tool_names and not default_all:
        query = query.where(
            (ToolDefinition.name.in_(allowed_tool_names)) | (ToolDefinition.id.in_(allowed_tool_names))
        )
    tool = db.scalar(query)
    if not tool or tool.is_builtin or tool.type == "builtin":
        return None
    return tool


def _allowed_tool_names(agent: Agent) -> list[str]:
    if agent_uses_default_full_permissions(agent):
        return list(BUILTIN_TOOLS.keys())
    configured = configured_tool_names(agent)
    return list(dict.fromkeys(configured))


def _db_tool_exists(db: Session, tool_name: str) -> bool:
    value = db.scalar(
        select(ToolDefinition.id).where(
            ToolDefinition.deleted_at.is_(None),
            ToolDefinition.status == "active",
            (ToolDefinition.name == tool_name) | (ToolDefinition.id == tool_name),
        )
    )
    return isinstance(value, str) and bool(value)
