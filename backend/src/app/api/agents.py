"""
Agents API

只负责 CRUD 和测试编排，LLM 调用统一走 model_provider。
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import Agent, User, utcnow
from app.schemas.common import (
    AgentCapabilityItemOut,
    AgentOut,
    AgentStatusItemOut,
    AgentTestOut,
    ApiResponse,
    IdDeletedOut,
    ListItems,
    PaginatedItems,
)
from app.schemas.requests import (
    CreateAgentRequest,
    GenerateAgentRequest,
    ParseCapabilitiesRequest,
    TestAgentRequest,
    UpdateAgentRequest,
)
from app.services.serialization import agent_to_dict
from app.services.model_config_resolver import create_provider_from_db
from app.services.tools.permissions import normalize_tool_names
from app.services.llm.gateway import test_model_config
from model_provider.core.interfaces import ChatMessage

router = APIRouter(tags=["agents"])


def _fallback_agent_spec(brief: str, preferred_tools: list[str] | None = None) -> dict:
    text = brief.strip() or "通用任务协作 Agent"
    capabilities = []
    dictionary = [
        ("前端", "编码"),
        ("React", "编码"),
        ("后端", "编码"),
        ("API", "架构"),
        ("数据", "架构"),
        ("测试", "测试"),
        ("审查", "质量"),
        ("部署", "运维"),
        ("文档", "文档"),
        ("产品", "产品"),
        ("检索", "RAG"),
    ]
    for label, category in dictionary:
        if label.lower() in text.lower():
            capabilities.append({"label": label, "category": category, "proficiency": 4})
    if not capabilities:
        capabilities = [{"label": "任务分析", "category": "通用", "proficiency": 4}]
    safe_name = re.sub(r"[^0-9A-Za-z一-龥]+", " ", text).strip()[:18] or "自定义 Agent"
    return {
        "name": f"{safe_name} Agent",
        "display_name": f"{safe_name} Agent",
        "description": f'面向"{text[:80]}"的自定义协作 Agent。',
        "capabilities": capabilities[:6],
        "system_prompt": f"你是 {safe_name} Agent，负责处理以下方向：{text}。输出必须结构清晰。",
        "tools": preferred_tools or ["file.extract_text", "file.summarize"],
        "temperature": 0.4,
    }


def _parse_json_object(text: str) -> dict | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def _model_provider(db: AsyncSession, prefer_config_id: str | None = None):
    return await create_provider_from_db(db, prefer_config_id)


@router.get("/agents", response_model=ApiResponse[PaginatedItems[AgentOut]])
async def list_agents(
    page: int = 1,
    page_size: int = 20,
    type: str = "all",
    status: str = "all",
    provider: str = "all",
    capability: str | None = None,
    sort_by: str = "default",
    sort_order: str = "desc",
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """分页查询 Agent 列表。

    Args:
        page: 页码，从 1 开始。
        page_size: 每页数量。
        type: 按类型筛选，如 "custom" / "official" / "all"。
        status: 按状态筛选，支持逗号分隔多选。
        provider: 按模型提供商筛选。
        capability: 按能力标签筛选，支持逗号分隔多选。
        sort_by: 排序字段，如 "default" / "response_time" / "type"。
        sort_order: 排序方向，"asc" 或 "desc"。
        search: 关键词搜索，匹配名称和描述。
        db: 数据库会话。
        _user: 当前认证用户。

    Returns:
        分页后的 Agent 列表及元数据。
    """
    query = select(Agent).where(Agent.deleted_at.is_(None))
    if type != "all":
        query = query.where(Agent.type == type)
    if status != "all":
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        query = query.where(Agent.status.in_(statuses))
    agents = (await db.scalars(query)).all()
    items = [agent_to_dict(agent) for agent in agents]
    items = [item for item in items if not _is_acceptance_agent_item(item)]
    if provider != "all":
        items = [it for it in items if it.get("provider") == provider]
    if capability:
        caps = {s.strip().lower() for s in capability.split(",") if s.strip()}
        items = [
            it for it in items if caps & {c["label"].lower() for c in it.get("capabilities", [])}
        ]
    if search:
        needle = search.lower()
        items = [
            it
            for it in items
            if needle in it["name"].lower()
            or needle in (it.get("display_name") or "").lower()
            or needle in it.get("description", "").lower()
        ]
    reverse = sort_order != "asc"
    if sort_by == "response_time":
        items.sort(key=lambda it: it.get("response_latency_ms", 0), reverse=reverse)
    elif sort_by == "type":
        items.sort(key=lambda it: it.get("type", ""), reverse=reverse)
    else:
        rank = {"online": 0, "degraded": 1, "offline": 2, "maintenance": 3}
        items.sort(
            key=lambda it: (
                rank.get(it.get("status", ""), 9),
                not it.get("is_official", False),
                it["name"],
            )
        )
    total = len(items)
    start = (page - 1) * page_size
    paged = items[start : start + page_size]
    return ok(
        {
            "items": paged,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": start + page_size < total,
            "has_prev": page > 1,
        }
    )


def _is_acceptance_agent_item(item: dict) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            item.get("name"),
            item.get("display_name"),
            item.get("description"),
        )
    ).lower()
    return "acceptance config agent" in text or "acceptance agent" in text


@router.get("/agents/status", response_model=ApiResponse[dict[str, AgentStatusItemOut]])
async def agent_status(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取所有 Agent 的状态摘要。

    Args:
        db: 数据库会话。
        _user: 当前认证用户。

    Returns:
        以 Agent ID 为键、状态摘要为值的字典。
    """
    agents = (await db.scalars(select(Agent).where(Agent.deleted_at.is_(None)))).all()
    return ok({agent.id: {"status": agent.status, "name": agent.name} for agent in agents})


@router.get("/agents/capabilities", response_model=ApiResponse[ListItems[AgentCapabilityItemOut]])
async def list_capabilities(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """获取系统中所有 Agent 的能力聚合列表。

    Args:
        db: 数据库会话。
        _user: 当前认证用户。

    Returns:
        能力标签列表，每项包含拥有该能力的 Agent 数量及最高熟练度。
    """
    agents = (await db.scalars(select(Agent).where(Agent.deleted_at.is_(None)))).all()
    capabilities: dict = {}
    for agent in agents:
        for cap in agent_to_dict(agent).get("capabilities", []):
            capabilities.setdefault(
                cap["label"],
                {
                    "label": cap["label"],
                    "category": cap["category"],
                    "agent_count": 0,
                    "max_proficiency": 0,
                },
            )
            capabilities[cap["label"]]["agent_count"] += 1
            capabilities[cap["label"]]["max_proficiency"] = max(
                capabilities[cap["label"]]["max_proficiency"], cap.get("proficiency", 0)
            )
    return ok({"items": list(capabilities.values())})


@router.post("/agents/parse-capabilities", response_model=ApiResponse[dict])
async def parse_capabilities(
    payload: ParseCapabilitiesRequest, _user: User = Depends(get_current_user)
):
    """从文本中解析能力标签。

    Args:
        payload: 包含待解析文本的请求体。
        _user: 当前认证用户。

    Returns:
        解析出的能力列表及推荐系统提示语。
    """
    text = payload.text.strip()
    dictionary = [
        ("前端", "编码"),
        ("React", "编码"),
        ("后端", "编码"),
        ("API", "架构"),
        ("数据库", "架构"),
        ("SQL", "编码"),
        ("测试", "测试"),
        ("审查", "质量"),
        ("部署", "运维"),
        ("文档", "文档"),
        ("产品", "产品"),
        ("知识库", "RAG"),
        ("检索", "RAG"),
    ]
    items = [
        {"label": label, "category": category, "proficiency": 4}
        for label, category in dictionary
        if label.lower() in text.lower()
    ]
    if not items:
        items = [{"label": "任务分析", "category": "通用", "proficiency": 3}]
    return ok({"items": items, "system_prompt": f"你是{text[:200]}。"})


@router.post("/agents/generate", response_model=ApiResponse[dict])
async def generate_agent(
    payload: GenerateAgentRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """基于自然语言描述生成 Agent 配置草案。

    Args:
        payload: 包含职责简述和偏好工具的生成请求。
        db: 数据库会话。
        _user: 当前认证用户。

    Returns:
        生成的 Agent 配置字段，包含 name、capabilities、system_prompt、tools 等。
    """
    brief = payload.brief.strip()
    if not brief:
        raise ValidationAppError("请先输入 Agent 目标或职责描述")
    fallback = _fallback_agent_spec(brief, payload.preferred_tools)
    provider = await _model_provider(db)
    if not provider:
        return ok(fallback, "Agent 配置已生成（mock 模式）")

    try:
        result = await provider.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是 AgentHub 的 Agent 配置生成器。只返回 JSON。字段：name, display_name, description, capabilities, system_prompt, tools, temperature。capabilities 每项包含 label, category, proficiency(1-5)。",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"brief": brief, "preferred_tools": payload.preferred_tools},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        generated = _parse_json_object(result.content) or fallback
    except Exception:
        generated = fallback

    normalized = {
        **fallback,
        **{k: v for k, v in generated.items() if v not in (None, "", [])},
    }
    normalized["capabilities"] = normalized.get("capabilities") or fallback["capabilities"]
    normalized["tools"] = normalize_tool_names(normalized.get("tools") or fallback["tools"])
    return ok(normalized, "Agent 配置已生成")


async def _get_agent(db: AsyncSession, agent_id: str) -> Agent:
    agent = await db.scalar(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
    if not agent:
        raise NotFoundError("Agent不存在")
    return agent


@router.get("/agents/{agent_id}", response_model=ApiResponse[AgentOut])
async def get_agent(
    agent_id: str, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    """根据 ID 获取单个 Agent 详情。

    Args:
        agent_id: Agent 唯一标识。
        db: 数据库会话。
        _user: 当前认证用户。

    Returns:
        完整的 Agent 配置和统计信息。
    """
    return ok(agent_to_dict(await _get_agent(db, agent_id)))


@router.post("/agents", response_model=ApiResponse[AgentOut])
async def create_agent(
    payload: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建自定义 Agent。

    Args:
        payload: Agent 创建请求，包含名称、类型、能力和配置等。
        db: 数据库会话。
        user: 当前认证用户，作为创建者。

    Returns:
        创建成功的 Agent 详情。
    """
    duplicate = await db.scalar(
        select(Agent).where(Agent.name == payload.name, Agent.deleted_at.is_(None))
    )
    if duplicate:
        raise ValidationAppError("Agent名称已存在")
    agent = Agent(
        owner_id=user.id,
        name=payload.name,
        type=payload.type,
        version=payload.version,
        status="online",
        description=payload.description,
        avatar_url=payload.avatar_url,
        capabilities=payload.capabilities,
        config={
            **payload.config,
            "system_prompt": payload.system_prompt,
            "tools": normalize_tool_names(payload.tools),
        },
        extra={
            "display_name": payload.display_name or payload.name,
            "avatar_color": payload.avatar_color or "#6B7280",
            "provider": payload.provider,
            "response_latency_ms": 1000,
            "success_rate": 0.99,
        },
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return ok(agent_to_dict(agent), "Agent 创建成功")


@router.patch("/agents/{agent_id}", response_model=ApiResponse[AgentOut])
async def update_agent(
    agent_id: str,
    payload: UpdateAgentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新指定 Agent 的配置。

    Args:
        agent_id: Agent 唯一标识。
        payload: 需要更新的字段，未提供的字段保持原值。
        db: 数据库会话。
        user: 当前认证用户，仅创建者或管理员可修改自定义 Agent。

    Returns:
        更新后的 Agent 详情。
    """
    agent = await _get_agent(db, agent_id)
    if agent.type == "custom" and agent.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只能修改自己创建的Agent")
    data = payload.model_dump(exclude_unset=True)
    for field in ["name", "description", "status", "avatar_url", "capabilities"]:
        if field in data:
            setattr(agent, field, data[field])
    if "display_name" in data:
        agent.extra = {**(agent.extra or {}), "display_name": data["display_name"]}
    if "avatar_color" in data:
        agent.extra = {**(agent.extra or {}), "avatar_color": data["avatar_color"]}
    config = dict(agent.config or {})
    if "system_prompt" in data:
        config["system_prompt"] = data["system_prompt"]
    if "config" in data and data["config"]:
        config.update(data["config"])
    if "tools" in data:
        config["tools"] = normalize_tool_names(data["tools"])
    agent.config = config
    await db.commit()
    await db.refresh(agent)
    return ok(agent_to_dict(agent), "Agent已更新")


@router.delete("/agents/{agent_id}", response_model=ApiResponse[IdDeletedOut])
async def delete_agent(
    agent_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    """删除自定义 Agent（官方 Agent 不可删除）。

    Args:
        agent_id: Agent 唯一标识。
        db: 数据库会话。
        user: 当前认证用户，仅创建者或管理员可删除。

    Returns:
        删除结果，包含被删除 Agent 的 ID。
    """
    agent = await _get_agent(db, agent_id)
    if agent.type != "custom":
        raise ForbiddenError("官方Agent不可删除")
    if agent.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只能删除自己创建的Agent")
    agent.deleted_at = utcnow()
    agent.status = "offline"
    await db.commit()
    return ok({"id": agent.id, "deleted": True})


@router.post("/agents/{agent_id}/test", response_model=ApiResponse[AgentTestOut])
async def test_agent(
    agent_id: str,
    payload: TestAgentRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """向指定 Agent 发送测试消息并返回响应。

    Args:
        agent_id: Agent 唯一标识。
        payload: 测试请求，包含待发送的消息内容。
        db: 数据库会话。
        _user: 当前认证用户。

    Returns:
        测试响应详情，包括 Agent 信息、请求内容、模型输出及延迟。
    """
    agent = await _get_agent(db, agent_id)
    model_config_id = (agent.config or {}).get("model_config_id")
    if model_config_id:
        result = await test_model_config(db, str(model_config_id), payload.message)
        return ok(
            {
                "agent": agent_to_dict(agent),
                "request": payload.message,
                "response": result.text,
                "model": result.model,
                "usage": result.usage,
                "latency_ms": (agent.extra or {}).get("response_latency_ms", 1000),
            },
            "娴嬭瘯瀹屾垚",
        )
    provider = await _model_provider(db, str(model_config_id) if model_config_id else None)
    system_prompt = (
        (agent.config or {}).get("system_prompt") or agent.description or f"你是 {agent.name}"
    )
    if not provider:
        response_text = f"[mock] {agent.name} received: {payload.message[:80]}"
        return ok(
            {
                "agent": agent_to_dict(agent),
                "request": payload.message,
                "response": response_text,
                "model": "mock",
                "usage": {},
                "latency_ms": 0,
            },
            "测试完成",
        )

    try:
        result = await provider.chat(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=payload.message),
            ],
        )
        response_text = result.content
        model = result.model or "unknown"
        usage = result.usage or {}
    except Exception as exc:
        response_text = f"[error] {exc}"
        model = "error"
        usage = {}

    return ok(
        {
            "agent": agent_to_dict(agent),
            "request": payload.message,
            "response": response_text,
            "model": model,
            "usage": usage,
            "latency_ms": (agent.extra or {}).get("response_latency_ms", 1000),
        },
        "测试完成",
    )
