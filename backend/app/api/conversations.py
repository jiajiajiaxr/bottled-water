from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import Agent, Conversation, ConversationParticipant, Message, User, WorkflowRun, Workspace, WorkspaceMember, utcnow
from app.schemas.requests import AddParticipantRequest, InviteParticipantRequest
from app.services.ark import ArkClient
from app.services.audit import write_audit_log
from app.services.serialization import conversation_to_dict, participant_to_dict, workflow_run_to_dict
from app.services.workflows.graph import Edge
from app.services.workflows.runtime import build_edge_states, build_node_states


router = APIRouter(tags=["conversations"])
compat_router = APIRouter(tags=["conversations-compat"])


async def _payload(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _conversation_query(user_id: str):
    return (
        select(Conversation)
        .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.agent))
        .where(Conversation.creator_id == user_id, Conversation.deleted_at.is_(None))
    )


def _accessible_workspace(db: Session, user: User, workspace_id: str | None) -> Workspace | None:
    if not workspace_id:
        return None
    member_workspace_ids = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == user.id,
        WorkspaceMember.left_at.is_(None),
    )
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.deleted_at.is_(None),
            (Workspace.owner_id == user.id) | (Workspace.id.in_(member_workspace_ids)),
        )
    )
    if not workspace:
        raise NotFoundError("Workspace not found")
    return workspace


def _conversation_workspace_id(conversation: Conversation) -> str | None:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    value = extra.get("workspace_id")
    return value if isinstance(value, str) and value else None


def _list(db: Session, user: User, workspace_id: str | None = None) -> list[dict]:
    _accessible_workspace(db, user, workspace_id)
    conversations = db.scalars(
        _conversation_query(user.id).order_by(
            Conversation.is_pinned.desc(),
            Conversation.last_message_at.desc().nullslast(),
            Conversation.updated_at.desc(),
        )
    ).all()
    if workspace_id:
        conversations = [item for item in conversations if _conversation_workspace_id(item) == workspace_id]
    else:
        conversations = [item for item in conversations if _conversation_workspace_id(item) is None]
    return [conversation_to_dict(item) for item in conversations]


def _create(db: Session, user: User, payload: dict) -> Conversation:
    workspace_id = payload.get("workspace_id")
    if workspace_id:
        _accessible_workspace(db, user, str(workspace_id))
    chat_type = payload.get("chat_type") or payload.get("type") or ("group" if payload.get("group") else "single")
    agents = db.scalars(select(Agent).where(Agent.deleted_at.is_(None))).all()
    requested = payload.get("participant_agent_ids") or payload.get("agent_ids") or []
    if requested:
        selected = [agent for agent in agents if agent.id in requested]
    elif chat_type == "group":
        selected = [agent for agent in agents if agent.type in {"master", "frontend", "backend", "reviewer"}]
    else:
        selected = [next((agent for agent in agents if agent.type == "master"), agents[0] if agents else None)]
        selected = [agent for agent in selected if agent is not None]
    if chat_type == "single" and len(selected) != 1:
        raise ValidationAppError("单聊会话只能包含1个Agent参与者")
    if chat_type == "group" and not (2 <= len(selected) <= 8):
        raise ValidationAppError("群聊会话参与者须为2-8个Agent")
    title = payload.get("title") or (
        "新的多 Agent 协作群" if chat_type == "group" else f"{selected[0].name} · 单聊"
    )
    conversation = Conversation(
        creator_id=user.id,
        chat_type=chat_type,
        title=title,
        description=payload.get("description") or "",
        extra={
            "workspace_id": str(workspace_id) if workspace_id else None,
            "master_enabled": bool(payload.get("master_enabled", chat_type == "group")),
            "category": payload.get("category") or "Default",
            "folder": payload.get("folder") or "Default",
            "remark": payload.get("remark") or "",
        },
        last_message_preview="会话已创建，可以发送任务开始协作。",
        last_message_sender="System",
        last_message_at=utcnow(),
        activity_score=50,
        message_count=1,
    )
    db.add(conversation)
    db.flush()
    for index, agent in enumerate(selected):
        db.add(
            ConversationParticipant(
                conversation_id=conversation.id,
                participant_type="agent",
                agent_id=agent.id,
                role="member",
            )
        )
    db.add(
        Message(
            conversation_id=conversation.id,
            sender_type="system",
            sender_name="System",
            content_type="event",
            content={"text": f"会话已创建，已加入 {len(selected)} 个 Agent。"},
            status="completed",
        )
    )
    db.commit()
    return db.scalars(_conversation_query(user.id).where(Conversation.id == conversation.id)).one()


def _get(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.scalar(_conversation_query(user.id).where(Conversation.id == conversation_id))
    if not conversation:
        raise NotFoundError("会话不存在")
    return conversation


def _active_participants(conversation: Conversation) -> list[ConversationParticipant]:
    return [item for item in conversation.participants if item.left_at is None]


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
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


WORKFLOW_NODE_TYPES = {"start", "agent", "tool", "skill", "mcp", "condition", "loop", "review", "artifact", "end"}


def _workflow_node_type(node: dict, role: str) -> str:
    raw_type = str(node.get("type") or "").lower().strip()
    if raw_type in WORKFLOW_NODE_TYPES:
        return raw_type
    normalized_role = role.lower().strip()
    if normalized_role in {"review", "reviewer"}:
        return "review"
    if normalized_role in {"artifact", "deploy", "delivery", "publish"}:
        return "artifact"
    if normalized_role in {"input", "start"}:
        return "start"
    if normalized_role == "end":
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
    agents = [item.agent for item in _active_participants(conversation) if item.agent]
    start_node = {
        "id": "start",
        "title": "Start",
        "type": "start",
        "role": "start",
        "status": "ready",
        "meta": "用户输入与上下文入口",
        "config": {"input": "message"},
    }
    end_node = {
        "id": "end",
        "title": "End",
        "type": "end",
        "role": "end",
        "status": "ready",
        "meta": "汇总最终回复",
        "config": {"output": "assistant_message"},
    }
    agent_nodes = [
        {
            "id": f"agent-{agent.id[:8]}",
            "title": (
                agent.extra.get("display_name")
                if isinstance(agent.extra, dict) and agent.extra.get("display_name")
                else agent.name
            ),
            "type": "review" if agent.type == "reviewer" else "agent",
            "role": agent.type or "agent",
            "status": agent.status,
            "meta": agent.description[:60] or agent.type,
            "agent_id": agent.id,
            "config": {
                "agent_id": agent.id,
                "model_config_id": (agent.config or {}).get("model_config_id"),
                "tools": (agent.config or {}).get("tools", []),
                "skill_ids": (agent.config or {}).get("skill_ids", []),
                "mcp_server_ids": (agent.config or {}).get("mcp_server_ids", []),
            },
        }
        for agent in agents[:8]
    ]
    edges = [["start", node["id"]] for node in agent_nodes]
    edges.extend([[node["id"], "end"] for node in agent_nodes])
    return {
        "conversation_id": conversation.id,
        "mode": "all_agents_independent",
        "nodes": [start_node, *agent_nodes, end_node],
        "edges": edges or [["start", "end"]],
        "settings": {
            "default_policy": "all active agents reply independently",
            "review_policy": "optional",
            "context_policy": "summary-window",
        },
    }
    worker_nodes = [
        {
            "id": f"agent-{agent.id[:8]}",
            "title": agent.name,
            "role": "worker",
            "status": agent.status,
            "meta": agent.description[:60] or agent.type,
            "agent_id": agent.id,
        }
        for agent in agents[:8]
    ]
    nodes = [
        {"id": "intake", "title": "需求入口", "role": "input", "status": "ready", "meta": "IM / 文件 / 上下文"},
        {"id": "master", "title": "Master Agent", "role": "master", "status": "ready", "meta": "拆解 / 排程 / 汇总"},
        *worker_nodes,
        {"id": "reviewer", "title": "Reviewer", "role": "reviewer", "status": "review", "meta": "质量门禁 / 风险审查"},
        {"id": "delivery", "title": "交付出口", "role": "artifact", "status": "publish", "meta": "回复 / 产物 / 部署"},
    ]
    worker_ids = [node["id"] for node in worker_nodes]
    edges = [["intake", "master"]]
    edges.extend(["master", worker_id] for worker_id in worker_ids)
    edges.extend([worker_id, "reviewer"] for worker_id in worker_ids)
    edges.append(["reviewer", "delivery"])
    if not worker_ids:
        edges = [["intake", "master"], ["master", "reviewer"], ["reviewer", "delivery"]]
    return {
        "conversation_id": conversation.id,
        "mode": "auto",
        "nodes": nodes,
        "edges": edges,
        "settings": {"review_policy": "review-required", "context_policy": "summary-window"},
    }


def _normalize_workflow(value: dict, conversation: Conversation) -> dict:
    fallback = _fallback_workflow(conversation)
    active_agent_ids = {item.agent_id for item in _active_participants(conversation) if item.agent_id}
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
            raw_meta = raw_meta.get("description") or ", ".join(str(item) for item in raw_meta.get("capabilities", [])[:3]) or ""
        elif isinstance(raw_meta, list):
            raw_meta = ", ".join(str(item) for item in raw_meta[:4])
        config = _node_config_defaults(node_type, node)
        agent_id = node.get("agent_id") or config.get("agent_id")
        if node_type in {"agent", "review"} and agent_id and str(agent_id) not in active_agent_ids:
            continue
        normalized_nodes.append(
            {
                "id": str(node.get("id") or f"node-{index + 1}"),
                "title": str(node.get("title") or node.get("name") or f"节点 {index + 1}")[:80],
                "type": node_type,
                "role": role,
                "status": str(node.get("status") or "ready"),
                "meta": str(raw_meta)[:160],
                "config": config,
                **({"agent_id": agent_id} if agent_id else {}),
            }
        )
    node_ids = {node["id"] for node in normalized_nodes}
    normalized_edges = []
    for raw_edge in edges[:80]:
        edge = Edge.from_value(raw_edge)
        if not edge or edge.source not in node_ids or edge.target not in node_ids:
            continue
        if edge.condition or edge.config:
            normalized_edges.append(
                {
                    "from": edge.source,
                    "to": edge.target,
                    **({"condition": edge.condition} if edge.condition else {}),
                    **({"config": edge.config} if edge.config else {}),
                }
            )
        else:
            normalized_edges.append([edge.source, edge.target])
    return {
        **fallback,
        **{key: value[key] for key in ("mode", "settings") if key in value},
        "nodes": normalized_nodes or fallback["nodes"],
        "edges": normalized_edges or fallback["edges"],
    }


def _ensure_workflow_tables(db: Session) -> None:
    WorkflowRun.__table__.create(bind=db.get_bind(), checkfirst=True)


def _new_node_states(workflow: dict) -> list[dict]:
    states = build_node_states(workflow)
    if states:
        states[0]["status"] = "running"
        states[0]["progress"] = 5
        states[0]["started_at"] = utcnow().isoformat()
    return states


def _sync_workflow_runtime(conversation: Conversation, run: WorkflowRun) -> None:
    conversation.extra = {
        **(conversation.extra or {}),
        "workflow_runtime": {
            "run_id": run.id,
            "status": run.status,
            "progress": run.progress,
            "node_states": run.node_states or [],
            "updated_at": utcnow().isoformat(),
        },
    }


def _patch(db: Session, user: User, conversation_id: str, payload: dict) -> Conversation:
    conversation = _get(db, user, conversation_id)
    action = payload.get("action")
    if not action:
        if "pinned" in payload:
            action = "pin" if payload["pinned"] else "unpin"
        elif "archived" in payload:
            action = "archive" if payload["archived"] else "unarchive"
        elif any(key in payload for key in ("title", "description", "remark", "category", "folder")):
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
        if title is None and any(key in payload for key in ("description", "remark", "category", "folder")):
            title = conversation.title
        if not title:
            raise ValidationAppError("标题不能为空")
        if title is not None:
            if not str(title).strip():
                raise ValidationAppError("title cannot be empty")
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
    db.commit()
    return _get(db, user, conversation.id)


@router.get("/conversations")
async def list_conversations(
    workspace_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = _list(db, user, workspace_id)
    return ok(
        {
            "items": items,
            "pinned": [item for item in items if item["is_pinned"]],
            "active": [item for item in items if item["status"] == "active" and not item["is_pinned"]],
            "archived": [item for item in items if item["status"] == "archived"],
            "counts": {"total": len(items)},
        }
    )


@router.post("/conversations")
async def create_conversation(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(conversation_to_dict(_create(db, user, await _payload(request))), "会话创建成功")


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(conversation_to_dict(_get(db, user, conversation_id)))


@router.get("/conversations/{conversation_id}/workflow")
async def get_conversation_workflow(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    workflow = (conversation.extra or {}).get("workflow")
    if not isinstance(workflow, dict):
        workflow = _fallback_workflow(conversation)
    return ok(_normalize_workflow(workflow, conversation))


@router.patch("/conversations/{conversation_id}/workflow")
async def update_conversation_workflow(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    workflow = _normalize_workflow(await _payload(request), conversation)
    workflow["settings"] = {**(workflow.get("settings") or {}), "edited_by_user": True}
    conversation.extra = {**(conversation.extra or {}), "workflow": workflow}
    db.commit()
    return ok(workflow, "工作流已保存")


@router.post("/conversations/{conversation_id}/workflow/generate")
async def generate_conversation_workflow(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    fallback = _fallback_workflow(conversation)
    agents = [
        {
            "id": item.agent.id,
            "name": item.agent.name,
            "type": item.agent.type,
            "description": item.agent.description,
            "capabilities": item.agent.capabilities,
        }
        for item in _active_participants(conversation)
        if item.agent
    ]
    generated = fallback
    payload = await _payload(request)
    instruction = str(payload.get("instruction") or payload.get("prompt") or "").strip()
    try:
        result = await ArkClient().chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Workflow nodes must include type and config. Allowed types: start, agent, tool, skill, mcp, condition, loop, review, artifact, end. "
                        "Use config for agent_id, tool_name, server_id, expression, branches, max_iterations and artifact_type. "
                        "你是 AgentHub 工作流编排器。只返回 JSON，不要 Markdown。"
                        "字段：mode, nodes, edges, settings。nodes 每项含 id,title,role,status,meta,agent_id。"
                        "根据群聊内 Agent 能力和用户的人工编排意见组织合理 DAG。"
                        "meta 必须是简短中文字符串，不要返回对象。Master 只负责擅长的编排/聚合，"
                        "如果人工意见要求并行或跳过 Master，也可以让 Worker 直接独立执行。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"conversation": conversation_to_dict(conversation), "agents": agents, "instruction": instruction},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.15,
            max_tokens=1400,
            purpose="workflow_generate",
        )
        generated = _parse_json_object(result.text) or fallback
    except Exception:
        generated = fallback
    workflow = _normalize_workflow(generated, conversation)
    workflow["settings"] = {**(workflow.get("settings") or {}), "generated_by_ai": True, "generation_instruction": instruction}
    conversation.extra = {**(conversation.extra or {}), "workflow": workflow}
    db.commit()
    return ok(workflow, "工作流已生成")


@router.get("/conversations/{conversation_id}/workflow/runs")
async def list_workflow_runs(
    conversation_id: str,
    latest: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_workflow_tables(db)
    conversation = _get(db, user, conversation_id)
    query = select(WorkflowRun).where(WorkflowRun.conversation_id == conversation.id).order_by(WorkflowRun.created_at.desc())
    if latest:
        run = db.scalars(query.limit(1)).first()
        return ok(workflow_run_to_dict(run) if run else None)
    runs = db.scalars(query.limit(50)).all()
    return ok({"items": [workflow_run_to_dict(item) for item in runs], "total": len(runs)})


@router.post("/conversations/{conversation_id}/workflow/runs")
async def start_workflow_run(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_workflow_tables(db)
    conversation = _get(db, user, conversation_id)
    payload = await _payload(request)
    workflow = (conversation.extra or {}).get("workflow")
    if not isinstance(workflow, dict):
        workflow = _fallback_workflow(conversation)
    workflow = _normalize_workflow(payload.get("workflow") if isinstance(payload.get("workflow"), dict) else workflow, conversation)
    run = WorkflowRun(
        conversation_id=conversation.id,
        trigger_message_id=payload.get("trigger_message_id"),
        started_by=user.id,
        status="running",
        mode=str(payload.get("mode") or workflow.get("mode") or "manual"),
        workflow_snapshot=workflow,
        node_states=_new_node_states(workflow),
        edge_states=build_edge_states(workflow),
        events=[{"type": "run.started", "at": utcnow().isoformat(), "actor_id": user.id}],
        progress=5,
        started_at=utcnow(),
    )
    db.add(run)
    db.flush()
    _sync_workflow_runtime(conversation, run)
    write_audit_log(
        db,
        user=user,
        action="workflow.run.start",
        target_type="conversation",
        target_id=conversation.id,
        detail={"run_id": run.id, "mode": run.mode},
        request=request,
        risk_score=0.15,
    )
    db.commit()
    db.refresh(run)
    return ok(workflow_run_to_dict(run), "Workflow run started")


@router.patch("/conversations/{conversation_id}/workflow/runs/{run_id}/nodes/{node_id}")
async def update_workflow_node_state(
    conversation_id: str,
    run_id: str,
    node_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _ensure_workflow_tables(db)
    conversation = _get(db, user, conversation_id)
    run = db.get(WorkflowRun, run_id)
    if not run or run.conversation_id != conversation.id:
        raise NotFoundError("Workflow run not found")
    payload = await _payload(request)
    states = list(run.node_states or [])
    found = False
    now = utcnow().isoformat()
    for state in states:
        if state.get("id") != node_id:
            continue
        found = True
        next_status = str(payload.get("status") or state.get("status") or "running")
        state["status"] = next_status
        if "progress" in payload:
            state["progress"] = max(0, min(100, int(payload.get("progress") or 0)))
        elif next_status in {"completed", "succeeded"}:
            state["progress"] = 100
        state["output"] = payload.get("output", state.get("output") or {})
        if state.get("type") == "condition" and "matched_branch" in payload:
            state["output"] = {**(state.get("output") or {}), "matched_branch": payload.get("matched_branch")}
        if state.get("type") == "loop":
            loop_output = dict(state.get("output") or {})
            if "current_iteration" in payload:
                loop_output["current_iteration"] = max(0, int(payload.get("current_iteration") or 0))
            if "max_iterations" in payload:
                loop_output["max_iterations"] = max(1, int(payload.get("max_iterations") or 1))
            state["output"] = loop_output
        state["message"] = payload.get("message", state.get("message"))
        if next_status in {"running", "reviewing"} and not state.get("started_at"):
            state["started_at"] = now
        if next_status in {"completed", "succeeded", "failed", "skipped"}:
            state["completed_at"] = now
        break
    if not found:
        raise NotFoundError("Workflow node not found")
    completed = len([item for item in states if item.get("status") in {"completed", "succeeded", "skipped"}])
    failed = any(item.get("status") == "failed" for item in states)
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
    run.events = [
        *(run.events or []),
        {
            "type": "node.updated",
            "node_id": node_id,
            "status": payload.get("status"),
            "at": now,
            "actor_id": user.id,
        },
    ][-200:]
    _sync_workflow_runtime(conversation, run)
    write_audit_log(
        db,
        user=user,
        action="workflow.node.update",
        target_type="workflow_run",
        target_id=run.id,
        detail={"node_id": node_id, "status": payload.get("status"), "progress": run.progress},
        request=request,
        risk_score=0.1,
    )
    db.commit()
    db.refresh(run)
    return ok(workflow_run_to_dict(run), "Workflow node state updated")


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(conversation_to_dict(_patch(db, user, conversation_id, await _payload(request))), "操作成功")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    conversation.deleted_at = utcnow()
    conversation.status = "deleted"
    db.commit()
    return ok({"id": conversation.id, "deleted_at": conversation.deleted_at.isoformat()})


@router.post("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    conversation.unread_count = 0
    db.commit()
    return ok({"id": conversation.id, "unread_count": 0})


@router.get("/conversations/{conversation_id}/participants")
@router.get("/conversations/{conversation_id}/members")
async def list_participants(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    return ok({"items": [participant_to_dict(item) for item in _active_participants(conversation)]})


@router.post("/conversations/{conversation_id}/participants")
@router.post("/conversations/{conversation_id}/members")
async def add_participants(
    conversation_id: str,
    payload: AddParticipantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    if conversation.chat_type != "group":
        raise ValidationAppError("只有群聊可以添加成员")
    existing_agent_ids = {item.agent_id for item in _active_participants(conversation) if item.agent_id}
    existing_user_ids = {item.user_id for item in _active_participants(conversation) if item.user_id}
    current_agents = len(existing_agent_ids)
    add_agents = [agent_id for agent_id in payload.agent_ids if agent_id not in existing_agent_ids]
    if current_agents + len(add_agents) > 8:
        raise ValidationAppError("群聊最多支持8个Agent")
    added: list[ConversationParticipant] = []
    if add_agents:
        agents = db.scalars(select(Agent).where(Agent.id.in_(add_agents), Agent.deleted_at.is_(None))).all()
        found = {agent.id for agent in agents}
        missing = set(add_agents) - found
        if missing:
            raise NotFoundError(f"Agent不存在：{', '.join(sorted(missing))}")
        for agent in agents:
            participant = ConversationParticipant(
                conversation_id=conversation.id,
                participant_type="agent",
                agent_id=agent.id,
                role=payload.role,
            )
            db.add(participant)
            added.append(participant)
    add_users = [user_id for user_id in payload.user_ids if user_id not in existing_user_ids]
    if add_users:
        users = db.scalars(select(User).where(User.id.in_(add_users), User.deleted_at.is_(None))).all()
        for member in users:
            participant = ConversationParticipant(
                conversation_id=conversation.id,
                participant_type="user",
                user_id=member.id,
                nickname=member.display_name,
                role=payload.role,
            )
            db.add(participant)
            added.append(participant)
    if added:
        db.flush()
        extra = dict(conversation.extra or {})
        workflow = extra.get("workflow")
        if not isinstance(workflow, dict) or not (workflow.get("settings") or {}).get("edited_by_user"):
            extra["workflow"] = _fallback_workflow(conversation)
            conversation.extra = extra
        conversation.last_message_preview = f"已加入 {len(added)} 位新成员"
        conversation.last_message_at = utcnow()
        conversation.activity_score += 3
        db.add(
            Message(
                conversation_id=conversation.id,
                sender_type="system",
                sender_name="System",
                content_type="event",
                content={"text": conversation.last_message_preview},
                status="completed",
            )
        )
    db.commit()
    db.expire_all()
    return ok(conversation_to_dict(_get(db, user, conversation.id)), "成员已加入")


@router.patch("/conversations/{conversation_id}/participants/{participant_id}")
async def update_participant_role(
    conversation_id: str,
    participant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    payload = await _payload(request)
    role = payload.get("role")
    if role not in {"owner", "admin", "member"}:
        raise ValidationAppError("角色必须是 owner/admin/member")
    participant = next((item for item in conversation.participants if item.id == participant_id), None)
    if not participant:
        raise NotFoundError("成员不存在")
    if role == "owner":
        for item in conversation.participants:
            if item.role == "owner":
                item.role = "admin"
    participant.role = role
    db.commit()
    return ok(participant_to_dict(participant), "成员角色已更新")


@router.delete("/conversations/{conversation_id}/participants/{participant_id}")
async def remove_participant(
    conversation_id: str,
    participant_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    participant = next((item for item in conversation.participants if item.id == participant_id and item.left_at is None), None)
    if not participant:
        raise NotFoundError("成员不存在")
    active_agents = [item for item in _active_participants(conversation) if item.participant_type == "agent"]
    if participant.participant_type == "agent" and len(active_agents) <= 1:
        raise ValidationAppError("群聊至少需要保留 1 个 Agent")
    if participant.participant_type != "agent" and participant.role == "owner":
        raise ValidationAppError("不能直接移除群主，请先转让群主")
    participant.left_at = utcnow()
    extra = dict(conversation.extra or {})
    workflow = extra.get("workflow")
    if not isinstance(workflow, dict) or not (workflow.get("settings") or {}).get("edited_by_user"):
        extra["workflow"] = _fallback_workflow(conversation)
        conversation.extra = extra
    conversation.last_message_preview = "群成员已移除"
    conversation.last_message_at = utcnow()
    db.add(
        Message(
            conversation_id=conversation.id,
            sender_type="system",
            sender_name="System",
            content_type="event",
            content={"text": conversation.last_message_preview},
            status="completed",
        )
    )
    db.commit()
    db.expire_all()
    return ok(conversation_to_dict(_get(db, user, conversation.id)), "成员已移除")


@router.post("/conversations/{conversation_id}/invites")
async def invite_participants(
    conversation_id: str,
    payload: InviteParticipantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    token = f"invite-{conversation.id[:8]}-{utcnow().timestamp():.0f}"
    conversation.extra = {
        **(conversation.extra or {}),
        "last_invite": {
            "token": token,
            "invitee_email": payload.invitee_email,
            "agent_ids": payload.agent_ids,
            "role": payload.role,
            "status": "pending",
        },
    }
    db.commit()
    return ok({"invite_token": token, "status": "pending", "conversation_id": conversation.id}, "邀请已创建")


@compat_router.get("/conversations")
async def compat_list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"items": _list(db, user)}


@compat_router.post("/conversations")
async def compat_create_conversation(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return conversation_to_dict(_create(db, user, await _payload(request)))


@compat_router.get("/conversations/{conversation_id}/participants")
@compat_router.get("/conversations/{conversation_id}/members")
async def compat_list_participants(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    return {"items": [participant_to_dict(item) for item in _active_participants(conversation)]}


@compat_router.post("/conversations/{conversation_id}/participants")
@compat_router.post("/conversations/{conversation_id}/members")
async def compat_add_participants(
    conversation_id: str,
    payload: AddParticipantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get(db, user, conversation_id)
    _ensure_can_manage(conversation, user)
    existing = {item.agent_id for item in _active_participants(conversation) if item.agent_id}
    agents = db.scalars(
        select(Agent).where(Agent.id.in_([item for item in payload.agent_ids if item not in existing]))
    ).all()
    for agent in agents:
        db.add(
            ConversationParticipant(
                conversation_id=conversation.id,
                participant_type="agent",
                agent_id=agent.id,
                role=payload.role,
            )
        )
    db.commit()
    db.expire_all()
    return conversation_to_dict(_get(db, user, conversation.id))
