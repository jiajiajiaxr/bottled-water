from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.services.agents.tool_loop import build_tools_for_agent
from app.services.chat.orchestrator import run_orchestration
from app.services.realtime.event_bus import event_bus
from app.services.tools.builtins.registry import BUILTIN_TOOLS
from app.services.tools.executor import invoke_tool
from app.services.tools.schema import validate_tool_arguments
from app.services.workflows.definition import _workflow_execution_order


def test_domain_service_imports_are_direct() -> None:
    assert callable(run_orchestration)
    assert callable(build_tools_for_agent)
    assert callable(invoke_tool)
    assert event_bus is not None


def test_legacy_capability_imports_are_reexport_shims() -> None:
    from app.services import artifact_exports, file_tools, mcp_runtime
    from app.services import agentic_runtime
    from app.services import ark, llm_gateway
    from app.services.agents import async_tool_loop
    from app.services.llm import ark as llm_ark
    from app.services.llm import gateway as llm_gateway_impl
    from app.services.mcp import invoke_mcp_tool_recorded, tool_name
    from app.services.tools import builtin_executor
    from app.services.tools.builtins.artifact import export as artifact_export
    from app.services.tools.builtins import file as builtin_file

    assert artifact_exports.export_artifact is artifact_export.export_artifact
    assert artifact_exports.default_export_format is artifact_export.default_export_format
    assert file_tools.extract_text_from_path is builtin_file.extract_text_from_path
    assert file_tools.convert_file is builtin_file.convert_file
    assert mcp_runtime.invoke_mcp_tool_recorded is invoke_mcp_tool_recorded
    assert mcp_runtime.tool_name is tool_name
    assert agentic_runtime.build_tools_for_agent is async_tool_loop.build_tools_for_agent
    assert agentic_runtime.execute_tool_by_name is async_tool_loop.execute_tool_by_name
    assert ark.ArkClient is llm_ark.ArkClient
    assert ark.LLMStreamEvent is llm_ark.LLMStreamEvent
    assert llm_gateway.stream_model_config_chat is llm_gateway_impl.stream_model_config_chat
    assert llm_gateway.test_model_config is llm_gateway_impl.test_model_config
    assert builtin_executor.invoke_builtin_tool


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
