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
    async for event in session.run("hello"):
        event_types.append(event.type)

    assert SCHEDULER_DECISION in event_types
    assert CONTROL_ASSIGN in event_types
    assert AGENT_REPORT in event_types
    assert CONTROL_COMPLETE in event_types
    assert session.get_status()["runtime"] == "actor"
