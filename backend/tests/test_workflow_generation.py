from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import conversations as conversations_api
from app.core.errors import ValidationAppError
from app.schemas.requests import WorkflowGeneratePayload
from app.services.workflows.runtime import _set_workflow_node_state, build_edge_states, build_node_states
from db.models import Agent, Base, Conversation, ConversationParticipant, User, WorkflowRun
from model_provider.core.interfaces import ChatResponse


def _agent(agent_id: str, name: str, agent_type: str) -> Agent:
    return Agent(
        id=agent_id,
        name=name,
        type=agent_type,
        status="online",
        description=f"{name} handles {agent_type} work",
        config={},
        capabilities=[],
    )


def _conversation() -> Conversation:
    frontend = _agent("agent-frontend", "Frontend Worker", "frontend")
    reviewer = _agent("agent-reviewer", "Reviewer", "reviewer")
    conversation = Conversation(
        id="conv-1",
        creator_id="user-1",
        chat_type="group",
        title="Workflow group",
        description="",
        extra={},
    )
    conversation.participants = [
        ConversationParticipant(
            id="p1",
            conversation_id=conversation.id,
            participant_type="agent",
            agent_id=frontend.id,
            agent=frontend,
        ),
        ConversationParticipant(
            id="p2",
            conversation_id=conversation.id,
            participant_type="agent",
            agent_id=reviewer.id,
            agent=reviewer,
        ),
        ConversationParticipant(
            id="p3",
            conversation_id=conversation.id,
            participant_type="user",
            user_id="user-1",
            role="owner",
        ),
    ]
    return conversation


def test_normalize_workflow_fills_missing_agent_id_from_node_intent() -> None:
    conversation = _conversation()
    raw = {
        "mode": "ai_generated",
        "nodes": [
            {"id": "start", "title": "Start", "type": "start"},
            {
                "id": "frontend-step",
                "title": "Frontend implementation",
                "type": "agent",
                "config": {},
            },
            {
                "id": "review-step",
                "title": "Review result",
                "type": "review",
                "config": {},
            },
            {"id": "end", "title": "End", "type": "end"},
        ],
        "edges": [
            ["start", "frontend-step"],
            ["frontend-step", "review-step"],
            ["review-step", "end"],
        ],
    }

    workflow = conversations_api._normalize_workflow(raw, conversation)
    by_id = {node["id"]: node for node in workflow["nodes"]}

    assert by_id["frontend-step"]["agent_id"] == "agent-frontend"
    assert by_id["frontend-step"]["config"]["agent_id"] == "agent-frontend"
    assert by_id["review-step"]["agent_id"] == "agent-reviewer"
    assert by_id["review-step"]["config"]["agent_id"] == "agent-reviewer"


def test_normalize_workflow_treats_id_only_start_and_end_as_control_nodes() -> None:
    conversation = _conversation()
    raw = {
        "mode": "canvas",
        "nodes": [
            {"id": "start", "title": "接收群聊输入"},
            {
                "id": "agent-step",
                "title": "Daily Chat Agent",
                "config": {"agent_id": "agent-frontend"},
            },
            {"id": "end", "title": "最终回复"},
        ],
        "edges": [["start", "agent-step"], ["agent-step", "end"]],
    }

    workflow = conversations_api._normalize_workflow(raw, conversation)
    by_id = {node["id"]: node for node in workflow["nodes"]}

    assert by_id["start"]["type"] == "start"
    assert by_id["start"]["role"] == "start"
    assert by_id["end"]["type"] == "end"
    assert by_id["end"]["role"] == "end"
    assert by_id["agent-step"]["type"] == "agent"
    assert by_id["agent-step"]["agent_id"] == "agent-frontend"
    assert workflow["edges"] == [["start", "agent-step"], ["agent-step", "end"]]


def test_workflow_node_state_updates_persist_json_fields(tmp_path) -> None:
    db_path = tmp_path / "workflow-json.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    workflow = {
        "mode": "manual",
        "nodes": [
            {"id": "start", "title": "Start", "type": "start"},
            {"id": "end", "title": "End", "type": "end"},
        ],
        "edges": [["start", "end"]],
    }
    try:
        with session_factory() as db:
            user = User(
                id="user-json",
                email="workflow-json@example.com",
                username="workflow-json",
                password_hash="x",
            )
            conversation = Conversation(
                id="conv-json",
                creator_id=user.id,
                chat_type="group",
                title="Workflow JSON",
                description="",
                extra={},
            )
            run = WorkflowRun(
                id="run-json",
                conversation_id=conversation.id,
                status="running",
                mode="manual",
                workflow_snapshot=workflow,
                node_states=build_node_states(workflow),
                edge_states=build_edge_states(workflow),
                events=[],
                progress=0,
            )
            db.add_all([user, conversation, run])
            db.commit()

            _set_workflow_node_state(
                run,
                "start",
                status="completed",
                progress=100,
                output={"text": "started"},
                message="Workflow started",
            )
            db.commit()

        with session_factory() as db:
            stored_run = db.get(WorkflowRun, "run-json")
            assert stored_run is not None
            start = next(state for state in stored_run.node_states if state["id"] == "start")
            assert start["status"] == "completed"
            assert start["progress"] == 100
            assert start["message"] == "Workflow started"
            assert start["output"]["text"] == "started"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.asyncio
async def test_generate_workflow_rejects_mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    conversation = _conversation()
    db = SimpleNamespace(commit=AsyncMock())
    user = SimpleNamespace(id="user-1", role="user")

    monkeypatch.setattr(conversations_api, "_get", AsyncMock(return_value=conversation))
    monkeypatch.setattr(conversations_api, "_model_provider", AsyncMock(return_value=None))

    with pytest.raises(ValidationAppError) as exc_info:
        await conversations_api.generate_conversation_workflow(
            conversation.id,
            WorkflowGeneratePayload(instruction="前后端并行，最后审查"),
            db=db,
            user=user,
        )

    assert "真实可用的模型" in exc_info.value.message


@pytest.mark.asyncio
async def test_generate_workflow_uses_model_json_and_normalizes_agent_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = _conversation()
    db = SimpleNamespace(commit=AsyncMock())
    user = SimpleNamespace(id="user-1", role="user")
    provider = SimpleNamespace(
        model="real-model",
        chat=AsyncMock(
            return_value=ChatResponse(
                content="""
                {
                  "mode": "ai_generated",
                  "nodes": [
                    {"id": "start", "title": "Start", "type": "start"},
                    {"id": "frontend", "title": "Frontend work", "type": "agent", "config": {}},
                    {"id": "end", "title": "End", "type": "end"}
                  ],
                  "edges": [["start", "frontend"], ["frontend", "end"]],
                  "settings": {}
                }
                """
            )
        ),
    )

    monkeypatch.setattr(conversations_api, "_get", AsyncMock(return_value=conversation))
    monkeypatch.setattr(conversations_api, "_model_provider", AsyncMock(return_value=provider))

    response = await conversations_api.generate_conversation_workflow(
        conversation.id,
        WorkflowGeneratePayload(instruction="让前端先处理"),
        db=db,
        user=user,
    )

    workflow = response["data"]
    frontend = next(node for node in workflow["nodes"] if node["id"] == "frontend")
    assert frontend["agent_id"] == "agent-frontend"
    assert frontend["config"]["agent_id"] == "agent-frontend"
    assert workflow["settings"]["generated_by"] == "model"
    assert workflow["settings"]["model"] == "real-model"
    provider.chat.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_workflow_run_failure_updates_node_states(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "workflow-run.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    workflow = {
        "mode": "manual",
        "nodes": [
            {"id": "start", "title": "Start", "type": "start"},
            {"id": "agent", "title": "Agent", "type": "agent", "agent_id": "agent-frontend"},
            {"id": "end", "title": "End", "type": "end"},
        ],
        "edges": [["start", "agent"], ["agent", "end"]],
    }
    try:
        with session_factory() as db:
            user = User(
                id="user-1",
                email="workflow@example.com",
                username="workflow",
                password_hash="x",
            )
            conversation = Conversation(
                id="conv-1",
                creator_id=user.id,
                chat_type="group",
                title="Workflow group",
                description="",
                extra={},
            )
            run = WorkflowRun(
                id="run-1",
                conversation_id=conversation.id,
                status="running",
                mode="manual",
                workflow_snapshot=workflow,
                node_states=conversations_api._new_node_states(workflow),
                edge_states=build_edge_states(workflow),
                events=[],
                progress=5,
            )
            db.add_all([user, conversation, run])
            db.commit()

        monkeypatch.setattr(conversations_api, "SessionLocal", session_factory)
        monkeypatch.setattr(
            conversations_api,
            "create_task_for_prompt",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("worker boot failed")),
        )
        publish = AsyncMock()
        monkeypatch.setattr(conversations_api.event_bus, "publish", publish)

        await conversations_api._execute_manual_workflow_run(
            conversation_id="conv-1",
            run_id="run-1",
            prompt="run it",
        )

        with session_factory() as db:
            stored_run = db.get(WorkflowRun, "run-1")
            stored_conversation = db.get(Conversation, "conv-1")
            assert stored_run is not None
            assert stored_conversation is not None
            states = {state["id"]: state for state in stored_run.node_states}
            assert stored_run.status == "failed"
            assert stored_run.progress == 100
            assert states["start"]["status"] == "failed"
            assert states["start"]["progress"] == 100
            assert states["start"]["error"] == "worker boot failed"
            assert states["agent"]["status"] == "skipped"
            assert states["end"]["status"] == "skipped"
            runtime = stored_conversation.extra["workflow_runtime"]
            assert runtime["status"] == "failed"
            assert runtime["node_states"][0]["status"] == "failed"
            assert any(event["type"] == "run.failed" for event in stored_run.events)
        publish.assert_awaited()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
