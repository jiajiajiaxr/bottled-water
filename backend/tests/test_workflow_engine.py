from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.graph import WorkflowGraph
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowNodeExecutor
from app.services.workflows.nodes.condition import ConditionNodeExecutor
from app.services.workflows.nodes.loop import LoopNodeExecutor
from app.services.workflows.nodes.base import resolve_references
from app.services.workflows.runtime import build_edge_states, build_node_states
from app.services.workflows.scheduler import WorkflowScheduler
from app.services.workflows.validator import validate_workflow_graph


def _workflow() -> dict[str, Any]:
    return {
        "mode": "canvas",
        "nodes": [
            {"id": "start", "type": "start", "title": "Start"},
            {"id": "a", "type": "agent", "title": "Agent", "agent_id": "agent-1"},
            {"id": "end", "type": "end", "title": "End"},
        ],
        "edges": [["start", "a"], ["a", "end"]],
    }


def _runtime(workflow: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    db = MagicMock()
    conversation = SimpleNamespace(id="conv-1", creator_id="user-1", extra={})
    user_message = SimpleNamespace(id="msg-1", extra={})
    task = SimpleNamespace(id="task-1", progress=0, output={})
    run = SimpleNamespace(
        id="run-1",
        status="running",
        progress=0,
        node_states=build_node_states(workflow),
        edge_states=build_edge_states(workflow),
        events=[],
        completed_at=None,
    )
    return db, conversation, user_message, task, run


def test_workflow_graph_topological_levels_and_branch_paths() -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "cond", "type": "condition"},
            {"id": "yes", "type": "tool"},
            {"id": "no", "type": "tool"},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            ["start", "cond"],
            {"from": "cond", "to": "yes", "condition": "true"},
            {"from": "cond", "to": "no", "condition": "false"},
            ["yes", "end"],
            ["no", "end"],
        ],
    }

    graph = WorkflowGraph.from_workflow(workflow)

    assert [node.id for node in graph.topological_sort()] == ["start", "cond", "yes", "no", "end"]
    assert {node.id for node in WorkflowScheduler(graph).parallel_levels()[2]} == {"yes", "no"}
    assert graph.skipped_targets_for_branch("cond", "true") == {"no"}


def test_workflow_validator_rejects_cycles_and_loop_overflow() -> None:
    cyclic = {
        "nodes": [{"id": "a", "type": "start"}, {"id": "b", "type": "loop", "config": {"max_iterations": 99}}],
        "edges": [["a", "b"], ["b", "a"]],
    }

    result = validate_workflow_graph(cyclic)

    assert not result.ok
    assert any("cycle" in item for item in result.errors)
    assert any("max_iterations" in item for item in result.errors)


def test_node_output_reference_resolution() -> None:
    value = {
        "prompt": "Use {{agent.text}}",
        "items": ["{{agent.nested.value}}", "plain"],
    }

    resolved = resolve_references(value, {"agent": {"text": "hello", "nested": {"value": 3}}})

    assert resolved == {"prompt": "Use hello", "items": ["3", "plain"]}


@pytest.mark.asyncio
async def test_condition_and_loop_nodes_record_runtime() -> None:
    context = SimpleNamespace(prompt="please build frontend", outputs={})
    condition = await ConditionNodeExecutor().execute(
        SimpleNamespace(id="cond", type="condition", config={"expression": "contains('frontend')", "branches": ["hit", "miss"]}),
        context,
    )
    loop = await LoopNodeExecutor().execute(SimpleNamespace(id="loop", type="loop", config={"max_iterations": 2}), context)

    assert condition.branch == "hit"
    assert condition.output["matched_branch"] == "hit"
    assert loop.output == {"max_iterations": 2, "current_iteration": 2}


@pytest.mark.asyncio
async def test_engine_agent_node_uses_function_call_loop() -> None:
    workflow = _workflow()
    db, conversation, user_message, task, run = _runtime(workflow)
    agent = SimpleNamespace(id="agent-1", name="Backend Worker", deleted_at=None)
    db.get.return_value = agent
    assistant = SimpleNamespace(id="assistant-1")
    loop_result = SimpleNamespace(
        assistant=assistant,
        text="done",
        tool_context={"agent_name": "Backend Worker", "summary": "ok"},
    )

    with patch("app.services.workflows.nodes.agent.run_agent_function_call_loop", new_callable=AsyncMock) as call_loop:
        call_loop.return_value = loop_result
        with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
            result = await WorkflowEngine(
                db,
                conversation=conversation,
                user_message=user_message,
                task=task,
                workflow_run=run,
                workflow=workflow,
                prompt="hello",
                channel="conversation:conv-1",
                agents=[agent],
            ).run()

    call_loop.assert_awaited_once()
    assert result.outputs["a"]["text"] == "done"
    assert run.status == "completed"
    assert any(state["id"] == "a" and state["status"] == "completed" for state in run.node_states)


class FlakyExecutor(WorkflowNodeExecutor):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, node: Any, context: Any) -> NodeExecutionResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary")
        return NodeExecutionResult(output={"ok": True}, retries=1)


@pytest.mark.asyncio
async def test_engine_retry_and_cancel_paths() -> None:
    workflow = {
        "nodes": [
            {"id": "tool", "type": "tool", "config": {"retry": 1, "tool_name": "api.test"}},
        ],
        "edges": [],
    }
    db, conversation, user_message, task, run = _runtime(workflow)
    flaky = FlakyExecutor()

    with patch("app.services.workflows.engine.get_executor", return_value=flaky):
        with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
            result = await WorkflowEngine(
                db,
                conversation=conversation,
                user_message=user_message,
                task=task,
                workflow_run=run,
                workflow=workflow,
                prompt="hello",
                channel="conversation:conv-1",
                agents=[],
            ).run()

    assert flaky.calls == 2
    assert result.outputs["tool"] == {"ok": True}

    cancelled_run = SimpleNamespace(**{**run.__dict__, "status": "cancelled", "events": []})
    with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
        cancelled = await WorkflowEngine(
            db,
            conversation=conversation,
            user_message=user_message,
            task=task,
            workflow_run=cancelled_run,
            workflow=workflow,
            prompt="hello",
            channel="conversation:conv-1",
            agents=[],
        ).run()
    assert cancelled.outputs == {}
    assert cancelled_run.status == "cancelled"
