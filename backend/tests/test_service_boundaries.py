from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.services.agents.tool_loop import build_tools_for_agent
from app.services.chat.orchestrator import run_orchestration
from app.services.realtime.event_bus import event_bus
from app.services.tools.builtins import BUILTIN_TOOLS
from app.services.tools.executor import invoke_tool
from app.services.tools.schema import validate_tool_arguments
from app.services.workflows.definition import _workflow_execution_order


def test_domain_service_imports_are_direct() -> None:
    assert callable(run_orchestration)
    assert callable(build_tools_for_agent)
    assert callable(invoke_tool)
    assert event_bus is not None


def test_tool_schema_validation_rejects_missing_required_field() -> None:
    schema = BUILTIN_TOOLS["artifact.create_pdf"].input_schema

    with pytest.raises(ValidationAppError, match="conversation_id"):
        validate_tool_arguments(schema, {}, tool_name="artifact.create_pdf")


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
