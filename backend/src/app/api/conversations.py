"""
Conversations API

会话 CRUD、成员管理和工作流编排，统一使用 model_provider。
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import Agent, Conversation, ConversationParticipant, Message, User, WorkflowRun, Workspace, WorkspaceMember, utcnow
from app.schemas.common import ApiResponse
from app.schemas.requests import (
    AddParticipantRequest, CreateConversationRequest, InviteParticipantRequest,
    ParticipantRoleUpdatePayload, UpdateConversationRequest, WorkflowGeneratePayload,
    WorkflowNodeUpdatePayload, WorkflowRunStartPayload, WorkflowUpdatePayload,
)
from app.services.audit import write_audit_log
from app.services.serialization import conversation_to_dict, participant_to_dict, workflow_run_to_dict
from model_provider import create_provider
from model_provider.core.config import ModelConfig
from app.core.config import get_settings

router = APIRouter(tags=["conversations"])
compat_router = APIRouter(tags=["conversations-compat"])

WORKFLOW_NODE_TYPES = {"start", "agent", "tool", "skill", "mcp", "condition", "loop", "review", "artifact", "end"}


def _model_provider():
    settings = get_settings()
    api_key = getattr(settings, "ARK_API_KEY", "")
    model = getattr(settings, "ARK_DEFAULT_MODEL", "ep-xxx")
    if not api_key:
        return None
    return create_provider(ModelConfig(provider="ark", model=model, api_key=api_key))


def _conversation_query(user_id: str):
    return select(Conversation).options(selectinload(Conversation.participants).selectinload(ConversationParticipant.agent)).where(Conversation.creator_id == user_id, Conversation.deleted_at.is_(None))


async def _accessible_workspace(db: AsyncSession, user: User, workspace_id: str | None) -> Workspace | None:
    if not workspace_id:
        return None
    member_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id, WorkspaceMember.left_at.is_(None))
    workspace = await db.scalar(select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None), (Workspace.owner_id == user.id) | (Workspace.id.in_(member_ids))))
    if not workspace:
        raise NotFoundError("Workspace not found")
    return workspace


def _conversation_workspace_id(conversation: Conversation) -> str | None:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    value = extra.get("workspace_id")
    return value if isinstance(value, str) and value else None


async def _list(db: AsyncSession, user: User, workspace_id: str | None = None) -> list[dict]:
    await _accessible_workspace(db, user, workspace_id)
    conversations = (await db.scalars(_conversation_query(user.id).order_by(Conversation.is_pinned.desc(), Conversation.last_message_at.desc().nullslast(), Conversation.updated_at.desc()))).all()
    if workspace_id:
        conversations = [it for it in conversations if _conversation_workspace_id(it) == workspace_id]
    else:
        conversations = [it for it in conversations if _conversation_workspace_id(it) is None]
    return [conversation_to_dict(it) for it in conversations]


async def _create(db: AsyncSession, user: User, payload: dict) -> Conversation:
    workspace_id = payload.get("workspace_id")
    if workspace_id:
        await _accessible_workspace(db, user, str(workspace_id))
    chat_type = payload.get("chat_type") or payload.get("type") or ("group" if payload.get("group") else "single")
    agents = (await db.scalars(select(Agent).where(Agent.deleted_at.is_(None)))).all()
    requested = payload.get("participant_agent_ids") or payload.get("agent_ids") or []
    if requested:
        selected = [a for a in agents if a.id in requested]
    elif chat_type == "group":
        selected = [a for a in agents if a.type in {"master", "frontend", "backend", "reviewer"}]
    else:
        selected = [next((a for a in agents if a.type == "master"), agents[0] if agents else None)]
        selected = [a for a in selected if a is not None]
    if chat_type == "single" and len(selected) != 1:
        raise ValidationAppError("单聊会话只能包含1个Agent参与者")
    if chat_type == "group" and not (2 <= len(selected) <= 8):
        raise ValidationAppError("群聊会话参与者须为2-8个Agent")
    title = payload.get("title") or ("新的多 Agent 协作群" if chat_type == "group" else f"{selected[0].name} · 单聊")
    conversation = Conversation(
        creator_id=user.id, chat_type=chat_type, title=title, description=payload.get("description") or "",
        extra={"workspace_id": str(workspace_id) if workspace_id else None, "master_enabled": bool(payload.get("master_enabled", chat_type == "group")), "category": payload.get("category") or "Default", "folder": payload.get("folder") or "Default", "remark": payload.get("remark") or ""},
        last_message_preview="会话已创建，可以发送任务开始协作。", last_message_sender="System", last_message_at=utcnow(),
        activity_score=50, message_count=1,
    )
    db.add(conversation)
    await db.flush()
    for agent in selected:
        db.add(ConversationParticipant(conversation_id=conversation.id, participant_type="agent", agent_id=agent.id, role="member"))
    db.add(Message(conversation_id=conversation.id, sender_type="system", sender_name="System", content_type="event", content={"text": f"会话已创建，已加入 {len(selected)} 个 Agent。"}, status="completed"))
    await db.commit()
    return (await db.scalars(_conversation_query(user.id).where(Conversation.id == conversation.id))).one()


async def _get(db: AsyncSession, user: User, conversation_id: str) -> Conversation:
    conv = await db.scalar(_conversation_query(user.id).where(Conversation.id == conversation_id))
    if not conv:
        raise NotFoundError("会话不存在")
    return conv


def _active_participants(conversation: Conversation) -> list[ConversationParticipant]:
    return [it for it in conversation.participants if it.left_at is None]


def _current_role(conversation: Conversation, user: User) -> str:
    if conversation.creator_id == user.id:
        return "owner"
    for participant in conversation.participants:
        if participant.user_id == user.id and participant.left_at is None:
            return participant.role
    return "member"


def _ensure_can_manage(conversation: Conversation, user: User) -> None:
    if _current_role(conversation, user) not in {"owner", "admin"} and user.role != "admin":
        raise ForbiddenError("只有群主或管理员可以管理群成员")


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


def _workflow_node_type(node: dict, role: str) -> str:
    raw_type = str(node.get("type") or "").lower().strip()
    if raw_type in WORKFLOW_NODE_TYPES:
        return raw_type
    normalized = role.lower().strip()
    if normalized in {"review", "reviewer"}:
        return "review"
    if normalized in {"artifact", "deploy", "delivery", "publish"}:
        return "artifact"
    if normalized in {"input", "start"}:
        return "start"
    if normalized == "end":
        return "end"
    return "agent"


def _node_config_defaults(node_type: str, node: dict) -> dict:
    raw_config = node.get("config") if isinstance(node.get("config"), dict) else {}
    config = dict(raw_config)
    if node.get("agent_id"):
        config.setdefault("agent_id", node.get("agent_id"))
    if node_type == "tool":
        config.setdefault("tool_name", node.get("tool_name") or node.get("name") or "")
    elif node_type == "skill":
        config.setdefault("skill_id", node.get("skill_id") or "")
    elif node_type == "mcp":
        config.setdefault("server_id", node.get("server_id") or "")
        config.setdefault("tool_name", node.get("tool_name") or "")
    elif node_type == "condition":
        config.setdefault("expression", node.get("expression") or "true")
        config.setdefault("branches", node.get("branches") if isinstance(node.get("branches"), list) else ["true", "false"])
    elif node_type == "loop":
        try:
            max_iterations = int(config.get("max_iterations") or node.get("max_iterations") or 3)
        except (TypeError, ValueError):
            max_iterations = 3
        config["max_iterations"] = max(1, min(max_iterations, 20))
    elif node_type == "artifact":
        config.setdefault("artifact_type", node.get("artifact_type") or "html")
    return config


def _fallback_workflow(conversation: Conversation) -> dict:
    agents = [it.agent for it in _active_participants(conversation) if it.agent]
    start_node = {"id": "start", "title": "Start", "type": "start", "role": "start", "status": "ready", "meta": "用户输入与上下文入口", "config": {"input": "message"}}
    end_node = {"id": "end", "title": "End", "type": "end", "role": "end", "status": "ready", "meta": "汇总最终回复", "config": {"output": "assistant_message"}}
    agent_nodes = [
        {
            "id": f"agent-{agent.id[:8]}",
            "title": (agent.extra.get("display_name") if isinstance(agent.extra, dict) and agent.extra.get("display_name") else agent.name),
            "type": "review" if agent.type == "reviewer" else "agent",
            "role": agent.type or "agent",
            "status": agent.status,
            "meta": agent.description[:60] or agent.type,
            "agent_id": agent.id,
            "config": {"agent_id": agent.id, "tools": (agent.config or {}).get("tools", []), "skill_ids": (agent.config or {}).get("skill_ids", []), "mcp_server_ids": (agent.config or {}).get("mcp_server_ids", [])},
        }
        for agent in agents[:8]
    ]
    edges = [["start", node["id"]] for node in agent_nodes]
    edges.extend([[node["id"], "end"] for node in agent_nodes])
    return {
        "conversation_id": conversation.id, "mode": "all_agents_independent",
        "nodes": [start_node, *agent_nodes, end_node],
        "edges": edges or [["start", "end"]],
        "settings": {"default_policy": "all active agents reply independently", "review_policy": "optional"},
    }


def _normalize_workflow(value: dict, conversation: Conversation) -> dict:
    fallback = _fallback_workflow(conversation)
    active_agent_ids = {it.agent_id for it in _active_participants(conversation) if it.agent_id}
    nodes = value.get("nodes") if isinstance(value.get("nodes"), list) else fallback["nodes"]
    edges = value.get("edges") if isinstance(value.get("edges"), list) else fallback["edges"]
    normalized_nodes = []
    for index, node in enumerate(nodes[:40]):
        if not isinstance(node, dict):
            continue
        role = str(node.get("role") or node.get("type") or "agent")
        node_type = _workflow_node_type(node, role)
        raw_meta = node.get("meta") or node.get("description") or ""
        if isinstance(raw_meta, dict):
            raw_meta = ", ".join(str(it) for it in raw_meta.get("capabilities", [])[:3]) or ""
        elif isinstance(raw_meta, list):
            raw_meta = ", ".join(str(it) for it in raw_meta[:4])
        config = _node_config_defaults(node_type, node)
        agent_id = node.get("agent_id") or config.get("agent_id")
        if node_type in {"agent", "review"} and agent_id and str(agent_id) not in active_agent_ids:
            continue
        normalized_nodes.append({
            "id": str(node.get("id") or f"node-{index + 1}"),
            "title": str(node.get("title") or node.get("name") or f"节点 {index + 1}")[:80],
            "type": node_type, "role": role, "status": str(node.get("status") or "ready"),
            "meta": str(raw_meta)[:160], "config": config,
            **({"agent_id": agent_id} if agent_id else {}),
        })
    node_ids = {node["id"] for node in normalized_nodes}
    normalized_edges = [[str(edge[0]), str(edge[1])] for edge in edges[:80] if isinstance(edge, list) and len(edge) == 2 and str(edge[0]) in node_ids and str(edge[1]) in node_ids]
    return {**fallback, **{k: value[k] for k in ("mode", "settings") if k in value}, "nodes": normalized_nodes or fallback["nodes"], "edges": normalized_edges or fallback["edges"]}


async def _ensure_workflow_tables(db: AsyncSession) -> None:
    async def _create_tables(conn):
        await conn.run_sync(lambda sync_conn: WorkflowRun.__table__.create(bind=sync_conn, checkfirst=True))
    # For AsyncSession, tables should already be created via migration; this is a no-op placeholder
    pass


def _new_node_states(workflow: dict) -> list[dict]:
    states = []
    for index, node in enumerate(workflow.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type") or "agent")
        config = node.get("config") if isinstance(node.get("config"), dict) else {}
        output = {}
        if node_type == "condition":
            branches = config.get("branches") if isinstance(config.get("branches"), list) else ["true", "false"]
            output = {"expression": config.get("expression") or "true", "matched_branch": branches[0] if branches else "default"}
        elif node_type == "loop":
            output = {"max_iterations": int(config.get("max_iterations") or 3), "current_iteration": 0}
        states.append({
            "id": str(node.get("id") or f"node-{index + 1}"),
            "title": str(node.get("title") or node.get("name") or f"Node {index + 1}"),
            "type": node_type, "role": str(node.get("role") or "worker"), "agent_id": node.get("agent_id"),
            "config": config, "status": "running" if index == 0 else "queued",
            "progress": 5 if index == 0 else 0, "output": output,
            "started_at": utcnow().isoformat() if index == 0 else None, "completed_at": None,
        })
    return states


def _sync_workflow_runtime(conversation: Conversation, run: WorkflowRun) -> None:
    conversation.extra = {**(conversation.extra or {}), "workflow_runtime": {"run_id": run.id, "status": run.status, "progress": run.progress, "node_states": run.node_states or [], "updated_at": utcnow().isoformat()}}


async def _patch(db: AsyncSession, user: User, conversation_id: str, payload: dict) -> Conversation:
    conversation = await _get(db, user, conversation_id)
    action = payload.get("action")
    if not action:
        if "pinned" in payload:
            action = "pin" if payload["pinned"] else "unpin"
        elif "archived" in payload:
            action = "archive" if payload["archived"] else "unarchive"
        elif any(k in payload for k in ("title", "description", "remark", "category", "folder")):
            action = "rename"
    if action == "pin":
        conversation.is_pinned = True
        conversation.pinned_at = utcnow()
    elif action == "unpin":
        conversation.is_pinned = False
        conversation.pinned_at = None
    elif action == "archive":
        conversation.status = "archived"
    elif action == "unarchive":
        conversation.status = "active"
    elif action == "rename":
        title = payload.get("title")
        if title is None and any(k in payload for k in ("description", "remark", "category", "folder")):
            title = conversation.title
        if not title:
            raise ValidationAppError("标题不能为空")
        conversation.title = str(title).strip()[:200]
        if payload.get("description") is not None:
            conversation.description = str(payload.get("description") or "")[:1000]
        extra = dict(conversation.extra or {})
        for key in ("remark", "category", "folder"):
            if key in payload:
                value = str(payload.get(key) or "").strip()
                extra[key] = value[:120] if value else ("Default" if key in {"category", "folder"} else "")
        conversation.extra = extra
    else:
        raise ValidationAppError("不支持的操作类型")
    await db.commit()
    return await _get(db, user, conversation.id)


@router.get("/conversations", response_model=ApiResponse[dict])
async def list_conversations(workspace_id: str | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    items = await _list(db, user, workspace_id)
    return ok({"items": items, "pinned": [it for it in items if it["is_pinned"]], "active": [it for it in items if it["status"] == "active" and not it["is_pinned"]], "archived": [it for it in items if it["status"] == "archived"], "counts": {"total": len(items)}})


@router.post("/conversations", response_model=ApiResponse[dict])
async def create_conversation(payload: CreateConversationRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(conversation_to_dict(await _create(db, user, payload.model_dump())), "会话创建成功")


@router.get("/conversations/{conversation_id}", response_model=ApiResponse[dict])
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(conversation_to_dict(await _get(db, user, conversation_id)))


@router.get("/conversations/{conversation_id}/workflow", response_model=ApiResponse[dict])
async def get_conversation_workflow(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    workflow = (conversation.extra or {}).get("workflow")
    if not isinstance(workflow, dict):
        workflow = _fallback_workflow(conversation)
    return ok(_normalize_workflow(workflow, conversation))


@router.patch("/conversations/{conversation_id}/workflow", response_model=ApiResponse[dict])
async def update_conversation_workflow(conversation_id: str, payload: WorkflowUpdatePayload, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    workflow = _normalize_workflow(payload.model_dump(), conversation)
    workflow["settings"] = {**(workflow.get("settings") or {}), "edited_by_user": True}
    conversation.extra = {**(conversation.extra or {}), "workflow": workflow}
    await db.commit()
    return ok(workflow, "工作流已保存")


@router.post("/conversations/{conversation_id}/workflow/generate", response_model=ApiResponse[dict])
async def generate_conversation_workflow(conversation_id: str, payload: WorkflowGeneratePayload, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    fallback = _fallback_workflow(conversation)
    agents = [{"id": it.agent.id, "name": it.agent.name, "type": it.agent.type, "description": it.agent.description, "capabilities": it.agent.capabilities} for it in _active_participants(conversation) if it.agent]
    generated = fallback
    provider = _model_provider()
    if provider:
        try:
            result = await provider.chat(
                messages=[
                    {"role": "system", "content": "你是 AgentHub 工作流编排器。只返回 JSON。字段：mode, nodes, edges, settings。nodes 含 id,title,role,status,meta,agent_id,config。Allowed types: start, agent, tool, skill, mcp, condition, loop, review, artifact, end。根据 Agent 能力组织合理 DAG。"},
                    {"role": "user", "content": json.dumps({"conversation": conversation_to_dict(conversation), "agents": agents, "instruction": payload.instruction or payload.prompt or ""}, ensure_ascii=False)},
                ],
                temperature=0.15,
                max_tokens=1400,
            )
            generated = _parse_json_object(result.content) or fallback
        except Exception:
            generated = fallback
    else:
        generated = fallback

    workflow = _normalize_workflow(generated, conversation)
    workflow["settings"] = {**(workflow.get("settings") or {}), "generated_by_ai": True}
    conversation.extra = {**(conversation.extra or {}), "workflow": workflow}
    await db.commit()
    return ok(workflow, "工作流已生成")


@router.get("/conversations/{conversation_id}/workflow/runs", response_model=ApiResponse[dict])
async def list_workflow_runs(conversation_id: str, latest: bool = False, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _ensure_workflow_tables(db)
    conversation = await _get(db, user, conversation_id)
    query = select(WorkflowRun).where(WorkflowRun.conversation_id == conversation.id).order_by(WorkflowRun.created_at.desc())
    if latest:
        run = (await db.scalars(query.limit(1))).first()
        return ok(workflow_run_to_dict(run) if run else None)
    runs = (await db.scalars(query.limit(50))).all()
    return ok({"items": [workflow_run_to_dict(it) for it in runs], "total": len(runs)})


@router.post("/conversations/{conversation_id}/workflow/runs", response_model=ApiResponse[dict])
async def start_workflow_run(conversation_id: str, payload: WorkflowRunStartPayload, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _ensure_workflow_tables(db)
    conversation = await _get(db, user, conversation_id)
    payload_dict = payload.model_dump()
    workflow = (conversation.extra or {}).get("workflow")
    if not isinstance(workflow, dict):
        workflow = _fallback_workflow(conversation)
    workflow = _normalize_workflow(payload_dict.get("workflow") if isinstance(payload_dict.get("workflow"), dict) else workflow, conversation)
    run = WorkflowRun(
        conversation_id=conversation.id, trigger_message_id=payload_dict.get("trigger_message_id"),
        started_by=user.id, status="running", mode=str(payload_dict.get("mode") or workflow.get("mode") or "manual"),
        workflow_snapshot=workflow, node_states=_new_node_states(workflow),
        edge_states=[{"from": edge[0], "to": edge[1], "status": "waiting"} for edge in workflow.get("edges", []) if isinstance(edge, list) and len(edge) == 2],
        events=[{"type": "run.started", "at": utcnow().isoformat(), "actor_id": user.id}], progress=5, started_at=utcnow(),
    )
    db.add(run)
    await db.flush()
    _sync_workflow_runtime(conversation, run)
    await write_audit_log(db, user=user, action="workflow.run.start", target_type="conversation", target_id=conversation.id, detail={"run_id": run.id, "mode": run.mode}, request=None, risk_score=0.15)
    await db.commit()
    await db.refresh(run)
    return ok(workflow_run_to_dict(run), "Workflow run started")


@router.patch("/conversations/{conversation_id}/workflow/runs/{run_id}/nodes/{node_id}", response_model=ApiResponse[dict])
async def update_workflow_node_state(conversation_id: str, run_id: str, node_id: str, payload: WorkflowNodeUpdatePayload, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _ensure_workflow_tables(db)
    conversation = await _get(db, user, conversation_id)
    run = await db.get(WorkflowRun, run_id)
    if not run or run.conversation_id != conversation.id:
        raise NotFoundError("Workflow run not found")
    payload_dict = payload.model_dump()
    states = list(run.node_states or [])
    found = False
    now = utcnow().isoformat()
    for state in states:
        if state.get("id") != node_id:
            continue
        found = True
        next_status = str(payload_dict.get("status") or state.get("status") or "running")
        state["status"] = next_status
        if "progress" in payload_dict:
            state["progress"] = max(0, min(100, int(payload_dict.get("progress") or 0)))
        elif next_status in {"completed", "succeeded"}:
            state["progress"] = 100
        state["output"] = payload_dict.get("output", state.get("output") or {})
        if state.get("type") == "condition" and "matched_branch" in payload_dict:
            state["output"] = {**(state.get("output") or {}), "matched_branch": payload_dict.get("matched_branch")}
        if state.get("type") == "loop":
            loop_output = dict(state.get("output") or {})
            if "current_iteration" in payload_dict:
                loop_output["current_iteration"] = max(0, int(payload_dict.get("current_iteration") or 0))
            if "max_iterations" in payload_dict:
                loop_output["max_iterations"] = max(1, int(payload_dict.get("max_iterations") or 1))
            state["output"] = loop_output
        state["message"] = payload_dict.get("message", state.get("message"))
        if next_status in {"running", "reviewing"} and not state.get("started_at"):
            state["started_at"] = now
        if next_status in {"completed", "succeeded", "failed", "skipped"}:
            state["completed_at"] = now
        break
    if not found:
        raise NotFoundError("Workflow node not found")
    completed = len([it for it in states if it.get("status") in {"completed", "succeeded", "skipped"}])
    failed = any(it.get("status") == "failed" for it in states)
    total = max(1, len(states))
    run.node_states = states
    run.progress = int((completed / total) * 100)
    if failed:
        run.status = "failed"
        run.completed_at = utcnow()
    elif completed == total:
        run.status = "completed"
        run.progress = 100
        run.completed_at = utcnow()
    else:
        run.status = "running"
    run.events = [*[it for it in (run.events or []) if isinstance(it, dict)], {"type": "node.updated", "node_id": node_id, "status": payload_dict.get("status"), "at": now, "actor_id": user.id}][-200:]
    _sync_workflow_runtime(conversation, run)
    await write_audit_log(db, user=user, action="workflow.node.update", target_type="workflow_run", target_id=run.id, detail={"node_id": node_id, "status": payload_dict.get("status"), "progress": run.progress}, request=None, risk_score=0.1)
    await db.commit()
    await db.refresh(run)
    return ok(workflow_run_to_dict(run), "Workflow node state updated")


@router.patch("/conversations/{conversation_id}", response_model=ApiResponse[dict])
async def update_conversation(conversation_id: str, payload: UpdateConversationRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(conversation_to_dict(await _patch(db, user, conversation_id, payload.model_dump())), "操作成功")


@router.delete("/conversations/{conversation_id}", response_model=ApiResponse[dict])
async def delete_conversation(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    conversation.deleted_at = utcnow()
    conversation.status = "deleted"
    await db.commit()
    return ok({"id": conversation.id, "deleted_at": conversation.deleted_at.isoformat()})


@router.post("/conversations/{conversation_id}/read", response_model=ApiResponse[dict])
async def mark_read(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    conversation.unread_count = 0
    await db.commit()
    return ok({"id": conversation.id, "unread_count": 0})


@router.get("/conversations/{conversation_id}/participants", response_model=ApiResponse[dict])
@router.get("/conversations/{conversation_id}/members", response_model=ApiResponse[dict])
async def list_participants(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    return ok({"items": [participant_to_dict(it) for it in _active_participants(conversation)]})


@router.post("/conversations/{conversation_id}/participants", response_model=ApiResponse[dict])
@router.post("/conversations/{conversation_id}/members", response_model=ApiResponse[dict])
async def add_participants(conversation_id: str, payload: AddParticipantRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    if conversation.chat_type != "group":
        raise ValidationAppError("只有群聊可以添加成员")
    existing_agent_ids = {it.agent_id for it in _active_participants(conversation) if it.agent_id}
    existing_user_ids = {it.user_id for it in _active_participants(conversation) if it.user_id}
    current_agents = len(existing_agent_ids)
    add_agents = [aid for aid in payload.agent_ids if aid not in existing_agent_ids]
    if current_agents + len(add_agents) > 8:
        raise ValidationAppError("群聊最多支持8个Agent")
    added: list[ConversationParticipant] = []
    if add_agents:
        agents = (await db.scalars(select(Agent).where(Agent.id.in_(add_agents), Agent.deleted_at.is_(None)))).all()
        found = {a.id for a in agents}
        missing = set(add_agents) - found
        if missing:
            raise NotFoundError(f"Agent不存在：{', '.join(sorted(missing))}")
        for agent in agents:
            db.add(ConversationParticipant(conversation_id=conversation.id, participant_type="agent", agent_id=agent.id, role=payload.role))
            added.append(ConversationParticipant(conversation_id=conversation.id, participant_type="agent", agent_id=agent.id, role=payload.role))
    add_users = [uid for uid in payload.user_ids if uid not in existing_user_ids]
    if add_users:
        users = (await db.scalars(select(User).where(User.id.in_(add_users), User.deleted_at.is_(None)))).all()
        for member in users:
            participant = ConversationParticipant(conversation_id=conversation.id, participant_type="user", user_id=member.id, nickname=member.display_name, role=payload.role)
            db.add(participant)
            added.append(participant)
    if added:
        await db.flush()
        extra = dict(conversation.extra or {})
        if not isinstance(extra.get("workflow"), dict) or not (extra.get("workflow", {}).get("settings") or {}).get("edited_by_user"):
            extra["workflow"] = _fallback_workflow(conversation)
            conversation.extra = extra
        conversation.last_message_preview = f"已加入 {len(added)} 位新成员"
        conversation.last_message_at = utcnow()
        conversation.activity_score += 3
        db.add(Message(conversation_id=conversation.id, sender_type="system", sender_name="System", content_type="event", content={"text": conversation.last_message_preview}, status="completed"))
    await db.commit()
    await db.expire_all()
    return ok(conversation_to_dict(await _get(db, user, conversation.id)), "成员已加入")


@router.patch("/conversations/{conversation_id}/participants/{participant_id}", response_model=ApiResponse[dict])
async def update_participant_role(conversation_id: str, participant_id: str, payload: ParticipantRoleUpdatePayload, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    if payload.role not in {"owner", "admin", "member"}:
        raise ValidationAppError("角色必须是 owner/admin/member")
    participant = next((it for it in conversation.participants if it.id == participant_id), None)
    if not participant:
        raise NotFoundError("成员不存在")
    if payload.role == "owner":
        for it in conversation.participants:
            if it.role == "owner":
                it.role = "admin"
    participant.role = payload.role
    await db.commit()
    return ok(participant_to_dict(participant), "成员角色已更新")


@router.delete("/conversations/{conversation_id}/participants/{participant_id}", response_model=ApiResponse[dict])
async def remove_participant(conversation_id: str, participant_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    participant = next((it for it in conversation.participants if it.id == participant_id and it.left_at is None), None)
    if not participant:
        raise NotFoundError("成员不存在")
    active_agents = [it for it in _active_participants(conversation) if it.participant_type == "agent"]
    if participant.participant_type == "agent" and len(active_agents) <= 1:
        raise ValidationAppError("群聊至少需要保留 1 个 Agent")
    if participant.participant_type != "agent" and participant.role == "owner":
        raise ValidationAppError("不能直接移除群主，请先转让群主")
    participant.left_at = utcnow()
    extra = dict(conversation.extra or {})
    if not isinstance(extra.get("workflow"), dict) or not (extra.get("workflow", {}).get("settings") or {}).get("edited_by_user"):
        extra["workflow"] = _fallback_workflow(conversation)
        conversation.extra = extra
    conversation.last_message_preview = "群成员已移除"
    conversation.last_message_at = utcnow()
    db.add(Message(conversation_id=conversation.id, sender_type="system", sender_name="System", content_type="event", content={"text": conversation.last_message_preview}, status="completed"))
    await db.commit()
    await db.expire_all()
    return ok(conversation_to_dict(await _get(db, user, conversation.id)), "成员已移除")


@router.post("/conversations/{conversation_id}/invites", response_model=ApiResponse[dict])
async def invite_participants(conversation_id: str, payload: InviteParticipantRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    token = f"invite-{conversation.id[:8]}-{utcnow().timestamp():.0f}"
    conversation.extra = {**(conversation.extra or {}), "last_invite": {"token": token, "invitee_email": payload.invitee_email, "agent_ids": payload.agent_ids, "role": payload.role, "status": "pending"}}
    await db.commit()
    return ok({"invite_token": token, "status": "pending", "conversation_id": conversation.id}, "邀请已创建")


# compat routes
@compat_router.get("/conversations", response_model=dict)
async def compat_list_conversations(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return {"items": await _list(db, user)}


@compat_router.post("/conversations", response_model=dict)
async def compat_create_conversation(payload: CreateConversationRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return conversation_to_dict(await _create(db, user, payload.model_dump()))


@compat_router.get("/conversations/{conversation_id}/participants", response_model=dict)
@compat_router.get("/conversations/{conversation_id}/members", response_model=dict)
async def compat_list_participants(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    return {"items": [participant_to_dict(it) for it in _active_participants(conversation)]}


@compat_router.post("/conversations/{conversation_id}/participants", response_model=dict)
@compat_router.post("/conversations/{conversation_id}/members", response_model=dict)
async def compat_add_participants(conversation_id: str, payload: AddParticipantRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = await _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    existing = {it.agent_id for it in _active_participants(conversation) if it.agent_id}
    agents = (await db.scalars(select(Agent).where(Agent.id.in_([aid for aid in payload.agent_ids if aid not in existing])))).all()
    for agent in agents:
        db.add(ConversationParticipant(conversation_id=conversation.id, participant_type="agent", agent_id=agent.id, role=payload.role))
    await db.commit()
    await db.expire_all()
    return conversation_to_dict(await _get(db, user, conversation.id))