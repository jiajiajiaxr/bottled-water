import pytest

from agent_runtime.core.types import AgentConfig, AgentReport, AgentState, AgentWill
from agent_runtime.workflow.scheduler import WorkflowScheduler


def _parallel_workflow() -> dict:
    return {
        "nodes": [
            {"id": "start", "type": "start", "title": "Start"},
            {
                "id": "agent-a",
                "type": "agent",
                "title": "Agent A",
                "agent_id": "agent-a",
                "config": {"agent_id": "agent-a"},
            },
            {
                "id": "agent-b",
                "type": "agent",
                "title": "Agent B",
                "agent_id": "agent-b",
                "config": {"agent_id": "agent-b"},
            },
            {"id": "end", "type": "end", "title": "End"},
        ],
        "edges": [
            ["start", "agent-a"],
            ["start", "agent-b"],
            ["agent-a", "end"],
            ["agent-b", "end"],
        ],
    }


@pytest.mark.asyncio
async def test_workflow_scheduler_parallel_start_fanout_targets_all_agents() -> None:
    scheduler = WorkflowScheduler(
        agents={
            "agent-a": AgentConfig(id="agent-a", name="Agent A", system_prompt="", role="worker"),
            "agent-b": AgentConfig(id="agent-b", name="Agent B", system_prompt="", role="worker"),
        }
    )
    scheduler.set_workflow_context(_parallel_workflow(), "你们好")

    decision = await scheduler.make_decision(
        blackboard={"kv_state": {}},
        agent_reports=[
            AgentReport(agent_id="agent-a", state=AgentState.READY, will=AgentWill.EXECUTE),
            AgentReport(agent_id="agent-b", state=AgentState.READY, will=AgentWill.EXECUTE),
        ],
        conversation_context={"current_task": "你们好"},
    )

    assert decision.decision_type == "parallel"
    assert decision.target_agent_ids == ["agent-a", "agent-b"]
    assert decision.verification_agents == ["agent-a", "agent-b"]

    complete = await scheduler.make_decision(
        blackboard={"kv_state": {}},
        agent_reports=[
            AgentReport(agent_id="agent-a", state=AgentState.COMPLETED, will=AgentWill.COMPLETE),
            AgentReport(agent_id="agent-b", state=AgentState.COMPLETED, will=AgentWill.COMPLETE),
        ],
        conversation_context={"current_task": "你们好"},
    )

    assert complete.decision_type == "complete"
