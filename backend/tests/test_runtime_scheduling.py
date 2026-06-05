from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.chat.scheduling import resolve_scheduling_strategy
from app.services.conversation_session_manager import ConversationSessionManager
from app.services.runtime_service import OrchestratorService
from db.models import User


class FakeDb:
    def __init__(self) -> None:
        self.commits = 0

    async def get(self, model, record_id: str):
        if model is User:
            return SimpleNamespace(id=record_id, extra={})
        return None

    async def commit(self) -> None:
        self.commits += 1


class FakeRuntimeSession:
    def __init__(self, session_id: str = "session-1") -> None:
        self.session_id = session_id

    async def run(self, _prompt: str):
        if False:
            yield None


def _conversation(**overrides):
    data = {
        "id": "conv-1",
        "creator_id": "user-1",
        "chat_type": "group",
        "extra": {
            "workflow": {
                "nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}],
                "edges": [["start", "end"]],
            }
        },
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _agent(agent_id: str = "agent-1"):
    return SimpleNamespace(
        id=agent_id,
        name=f"Agent {agent_id}",
        type="worker",
        description="Worker agent",
        config={"tools": []},
    )


def test_group_with_workflow_defaults_to_auto_organization_until_enabled() -> None:
    conversation = _conversation()

    assert resolve_scheduling_strategy(conversation) == "tech_lead"
    conversation.extra["workflow_enabled"] = True
    conversation.extra["scheduling_strategy"] = "workflow"
    assert resolve_scheduling_strategy(conversation) == "workflow"
    assert resolve_scheduling_strategy(conversation, "tech_lead") == "tech_lead"

    conversation.extra["scheduling_strategy"] = "tech_lead"
    conversation.extra["workflow_enabled"] = False
    assert resolve_scheduling_strategy(conversation) == "tech_lead"


@pytest.mark.asyncio
async def test_create_session_honors_explicit_workflow_strategy() -> None:
    captured: dict = {}

    def create_session(**kwargs):
        captured.update(kwargs)
        return FakeRuntimeSession()

    conversation = _conversation(extra={"scheduling_strategy": "workflow", "workflow_enabled": True})
    db = FakeDb()
    with patch(
        "app.services.model_config_resolver.create_provider_from_db",
        new=AsyncMock(return_value=SimpleNamespace()),
    ):
        with patch("app.services.runtime_service.AgentSession.create", side_effect=create_session):
            await OrchestratorService.create_session(
                db,
                conversation,
                [_agent()],
                scheduling_strategy="workflow",
            )

    assert captured["scheduler_config"]["strategy"] == "workflow"
    assert captured["scheduler_config"]["workflow"]["nodes"]


@pytest.mark.asyncio
async def test_sse_orchestrator_run_passes_requested_strategy() -> None:
    session = FakeRuntimeSession()
    create_session = AsyncMock(return_value=session)
    conversation = _conversation(extra={})
    message = SimpleNamespace(content={"text": "hello"})

    with patch.object(OrchestratorService, "_get_conversation_agents", new=AsyncMock(return_value=[_agent(), _agent("agent-2")])):
        with patch.object(OrchestratorService, "create_session", new=create_session):
            await OrchestratorService.run(FakeDb(), conversation, message, "workflow")

    assert create_session.await_args.kwargs["scheduling_strategy"] == "workflow"


@pytest.mark.asyncio
async def test_session_manager_recreates_cached_session_when_strategy_changes() -> None:
    db = FakeDb()
    conversation = _conversation(extra={"scheduling_strategy": "workflow", "workflow_enabled": True})
    first = FakeRuntimeSession("session-workflow")
    second = FakeRuntimeSession("session-tech-lead")
    create_session = AsyncMock(side_effect=[first, second])
    manager = ConversationSessionManager()

    with patch.object(OrchestratorService, "_get_conversation_agents", new=AsyncMock(return_value=[_agent(), _agent("agent-2")])):
        with patch.object(OrchestratorService, "create_session", new=create_session):
            assert await manager.get_or_create_session(db, conversation) is first
            conversation.extra = {"scheduling_strategy": "tech_lead"}
            assert await manager.get_or_create_session(db, conversation) is second

    assert create_session.await_count == 2
    assert create_session.await_args.kwargs["scheduling_strategy"] == "tech_lead"
