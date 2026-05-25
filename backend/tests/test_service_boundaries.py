from __future__ import annotations

from app.services.agents.tool_loop import build_tools_for_agent
from app.services.chat.orchestrator import run_orchestration
from app.services.tools.executor import invoke_tool
from app.services.realtime.event_bus import event_bus
from app.services.workflows.definition import _workflow_execution_order


def test_domain_service_imports_are_direct() -> None:
    assert callable(run_orchestration)
    assert callable(build_tools_for_agent)
    assert callable(invoke_tool)
    assert event_bus is not None


def test_workflow_definition_keeps_dag_order() -> None:
    workflow = {
        "nodes": [
            {"id": "review", "title": "Review", "type": "review"},
            {"id": "start", "title": "Start", "type": "start"},
            {"id": "agent", "title": "Agent", "type": "agent"},
            {"id": "end", "title": "End", "type": "end"},
        ],
        "edges": [["start", "agent"], ["agent", "review"], ["review", "end"]],
    }

    assert [node["id"] for node in _workflow_execution_order(workflow)] == [
        "start",
        "agent",
        "review",
        "end",
    ]
