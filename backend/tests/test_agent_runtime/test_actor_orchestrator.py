import pytest
from model_provider import ChatResponse

from agent_runtime import AgentConfig, Session
from agent_runtime.core.protocol import AGENT_REPORT, CONTROL_ASSIGN, CONTROL_COMPLETE, SCHEDULER_DECISION


def test_actor_runtime_default_idle_timeout_is_extended(mock_provider, mock_tool_executor):
    session = Session.create(
        agents=[AgentConfig(id="frontend", name="Frontend", system_prompt="You are frontend.")],
        scheduler_config={"strategy": "tech_lead", "runtime": "actor"},
        model_provider=mock_provider,
        tool_executor=mock_tool_executor,
        session_id="sess_actor_timeout_default",
    )

    assert session.orchestrator.max_runtime_seconds == 1200.0


@pytest.mark.asyncio
async def test_actor_runtime_session_runs_scheduler_and_worker(mock_provider, mock_tool_executor):
    mock_provider.responses = [
        ChatResponse(
            content='{"decision_type":"assign","target_agent_id":"frontend","task_description":"say hello","rationale":"best fit"}'
        ),
        ChatResponse(
            content='hello done\n```status_report\n{"state":"completed","will":"complete","confidence":0.9}\n```'
        ),
        ChatResponse(content='{"decision_type":"complete","rationale":"worker completed"}'),
    ]
    session = Session.create(
        agents=[AgentConfig(id="frontend", name="Frontend", system_prompt="You are frontend.")],
        scheduler_config={"strategy": "tech_lead", "runtime": "actor", "max_runtime_seconds": 5},
        model_provider=mock_provider,
        tool_executor=mock_tool_executor,
        session_id="sess_actor_e2e",
    )

    event_types = []
    async for event in session.run("build a page"):
        event_types.append(event.type)

    assert SCHEDULER_DECISION in event_types
    assert CONTROL_ASSIGN in event_types
    assert AGENT_REPORT in event_types
    assert CONTROL_COMPLETE in event_types
    assert session.get_status()["runtime"] == "actor"


@pytest.mark.asyncio
async def test_actor_runtime_simple_greeting_uses_single_scheduler_path(mock_provider, mock_tool_executor):
    mock_provider.responses = [
        ChatResponse(
            content='hello from model\n```status_report\n{"state":"completed","will":"complete","confidence":0.9}\n```'
        ),
    ]
    session = Session.create(
        agents=[
            AgentConfig(id="daily", name="Daily Chat Agent", system_prompt="You are chat.", role="chat"),
            AgentConfig(id="backend", name="Backend", system_prompt="You are backend."),
        ],
        scheduler_config={"strategy": "tech_lead", "runtime": "actor", "max_runtime_seconds": 5},
        model_provider=mock_provider,
        tool_executor=mock_tool_executor,
        session_id="sess_actor_greeting",
    )

    events = []
    async for event in session.run("hello"):
        events.append(event)

    assignments = [event for event in events if event.type == CONTROL_ASSIGN]
    reports = [event for event in events if event.type == AGENT_REPORT and event.payload.get("work_product")]
    decisions = [event for event in events if event.type == SCHEDULER_DECISION]

    assert [event.target for event in assignments] == ["daily"]
    assert decisions[0].payload["decision"]["decision_type"] == "assign"
    assert decisions[-1].payload["decision"]["decision_type"] == "complete"
    assert len(reports) == 1
    assert reports[0].payload["agent_id"] == "daily"
    assert "hello from model" in reports[0].payload["work_product"]
    assert mock_provider.call_count == 1


@pytest.mark.asyncio
async def test_actor_runtime_mention_assigns_once_and_completes(mock_provider, mock_tool_executor):
    session = Session.create(
        agents=[
            AgentConfig(id="frontend", name="Frontend", system_prompt="You are frontend."),
            AgentConfig(id="backend", name="Backend", system_prompt="You are backend."),
        ],
        scheduler_config={"strategy": "tech_lead", "runtime": "actor", "max_runtime_seconds": 5},
        model_provider=mock_provider,
        tool_executor=mock_tool_executor,
        session_id="sess_actor_mention",
    )

    events = []
    async for event in session.run("@Frontend hello"):
        events.append(event)

    assignments = [event for event in events if event.type == CONTROL_ASSIGN]
    decisions = [event for event in events if event.type == SCHEDULER_DECISION]

    assert [event.target for event in assignments] == ["frontend"]
    assert decisions[0].payload["decision"]["decision_type"] == "assign"
    assert decisions[-1].payload["decision"]["decision_type"] == "complete"
    assert CONTROL_COMPLETE in [event.type for event in events]


@pytest.mark.asyncio
async def test_actor_runtime_structured_mention_metadata_does_not_create_second_round(mock_provider, mock_tool_executor):
    mock_provider.responses = [
        ChatResponse(
            content='deploy answer\n```status_report\n{"state":"completed","will":"complete","confidence":0.9}\n```'
        ),
        ChatResponse(
            content='{"decision_type":"assign","target_agent_id":"deploy","task_description":"repeat","rationale":"should not run"}'
        ),
    ]
    session = Session.create(
        agents=[
            AgentConfig(id="daily", name="Daily Chat Agent", system_prompt="You are chat.", role="chat"),
            AgentConfig(id="deploy", name="Deploy Agent", system_prompt="You are deploy.", role="deploy"),
        ],
        scheduler_config={"strategy": "tech_lead", "runtime": "actor", "max_runtime_seconds": 5},
        model_provider=mock_provider,
        tool_executor=mock_tool_executor,
        session_id="sess_actor_structured_mention",
    )

    events = []
    async for event in session.run(
        "## Required Agent Mentions\n- @Deploy Agent (agent_id=deploy)\n\n你会干嘛",
        context_metadata={
            "mention_target_agent_ids": ["deploy"],
            "agent_mentions": [{"agent_id": "deploy", "agent_name": "Deploy Agent"}],
        },
    ):
        events.append(event)

    assignments = [event for event in events if event.type == CONTROL_ASSIGN]
    decisions = [event for event in events if event.type == SCHEDULER_DECISION]

    assert [event.target for event in assignments] == ["deploy"]
    assert decisions[0].payload["decision"]["decision_type"] == "assign"
    assert decisions[-1].payload["decision"]["decision_type"] == "complete"
    assert mock_provider.call_count == 1
