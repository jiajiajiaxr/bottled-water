from __future__ import annotations

from app.services.agentic_runtime import build_tools_for_agent as legacy_build_tools_for_agent
from app.services.agents.tool_loop import build_tools_for_agent
from app.services.chat.orchestrator import run_orchestration
from app.services.events import event_bus as legacy_event_bus
from app.services.orchestrator import run_orchestration as legacy_run_orchestration
from app.services.tool_registry import invoke_tool as legacy_invoke_tool
from app.services.tools.executor import invoke_tool
from app.services.realtime.event_bus import event_bus
from app.services.workflows.definition import _workflow_execution_order


def test_legacy_service_shims_point_to_domain_modules() -> None:
    assert legacy_run_orchestration is run_orchestration
    assert legacy_build_tools_for_agent is build_tools_for_agent
    assert legacy_invoke_tool is invoke_tool
    assert legacy_event_bus is event_bus


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
