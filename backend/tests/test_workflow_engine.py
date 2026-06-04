from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest

from db.models import Agent, Conversation, Message, Task, User, WorkflowRun
from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.graph import WorkflowGraph
from app.services.workflows.io import resolve_node_input
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowNodeExecutor
from app.services.workflows.nodes.artifact import ArtifactNodeExecutor
from app.services.workflows.nodes.condition import ConditionNodeExecutor
from app.services.workflows.nodes.end import EndNodeExecutor
from app.services.workflows.nodes.loop import LoopNodeExecutor
from app.services.workflows.nodes.base import resolve_references
from app.services.workflows.nodes.tool import ToolNodeExecutor
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
        "nodes": [
            {"id": "a", "type": "start"},
            {"id": "b", "type": "loop", "config": {"max_iterations": 99}},
        ],
        "edges": [["a", "b"], ["b", "a"]],
    }

    result = validate_workflow_graph(cyclic)

    assert not result.ok
    assert any("cycle" in item for item in result.errors)
    assert any("max_iterations" in item for item in result.errors)


def test_workflow_validator_requires_reachable_complete_canvas() -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "agent", "type": "agent"},
            {"id": "tool", "type": "tool", "config": {}},
            {"id": "end", "type": "end"},
        ],
        "edges": [["start", "agent"]],
    }

    result = validate_workflow_graph(workflow)

    assert not result.ok
    assert any("must select an agent" in item for item in result.errors)
    assert any("tool_name" in item for item in result.errors)
    assert any("End node end is not reachable" in item for item in result.errors)


def test_node_output_reference_resolution() -> None:
    value = {
        "prompt": "Use {{agent.text}}",
        "items": ["{{agent.nested.value}}", "plain"],
    }

    resolved = resolve_references(value, {"agent": {"text": "hello", "nested": {"value": 3}}})

    assert resolved == {"prompt": "Use hello", "items": [3, "plain"]}


def test_node_input_resolver_supports_dify_style_references() -> None:
    workflow = {
        "nodes": [
            {"id": "source", "type": "tool"},
            {
                "id": "target",
                "type": "tool",
                "config": {
                    "input": {
                        "raw": "{{input}}",
                        "from_node": "{{nodes.source.text}}",
                        "joined": "{{upstream.text}}",
                    }
                },
            },
        ],
        "edges": [["source", "target"]],
    }
    graph = WorkflowGraph.from_workflow(workflow)
    node_input = resolve_node_input(
        node=graph.node_by_id["target"],
        graph=graph,
        prompt="原始需求",
        outputs={"source": {"text": "上游产物"}},
    )

    assert node_input["raw"] == "原始需求"
    assert node_input["from_node"] == "上游产物"
    assert "source: 上游产物" in node_input["joined"]


def test_runtime_node_states_include_input_output_error_fields() -> None:
    states = build_node_states(_workflow())

    assert states[0]["input"] == {}
    assert states[0]["output"] == {}
    assert states[0]["error"] is None


@pytest.mark.asyncio
async def test_condition_and_loop_nodes_record_runtime() -> None:
    context = SimpleNamespace(prompt="please build frontend", outputs={})
    condition = await ConditionNodeExecutor().execute(
        SimpleNamespace(
            id="cond",
            type="condition",
            config={"expression": "contains('frontend')", "branches": ["hit", "miss"]},
        ),
        context,
    )
    loop = await LoopNodeExecutor().execute(
        SimpleNamespace(id="loop", type="loop", config={"max_iterations": 2}), context
    )

    assert condition.branch == "hit"
    assert condition.output["matched_branch"] == "hit"
    assert loop.output["max_iterations"] == 2
    assert loop.output["current_iteration"] == 2


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

    with patch(
        "app.services.workflows.nodes.agent.run_agent_function_call_loop", new_callable=AsyncMock
    ) as call_loop:
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
    assert call_loop.await_args.kwargs["emit_message"] is True
    assert result.outputs["a"]["text"] == "done"
    assert run.status == "completed"
    assert any(state["id"] == "a" and state["status"] == "completed" for state in run.node_states)


@pytest.mark.asyncio
async def test_agent_node_receives_upstream_output_in_model_context() -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "source",
                "type": "tool",
                "config": {
                    "tool_name": "source.tool",
                    "output": {"text": "{{output.result.text}}"},
                },
            },
            {
                "id": "agent",
                "type": "agent",
                "agent_id": "agent-1",
                "title": "Writer",
                "config": {"input": {"brief": "{{nodes.source.text}}", "all": "{{upstream.text}}"}},
            },
            {"id": "end", "type": "end"},
        ],
        "edges": [["start", "source"], ["source", "agent"], ["agent", "end"]],
    }
    db, conversation, user_message, task, run = _runtime(workflow)
    agent = SimpleNamespace(id="agent-1", name="Writer", deleted_at=None, config={})
    user = SimpleNamespace(id="user-1")

    def get_model(model: Any, item_id: str) -> Any:
        if model is Agent and item_id == "agent-1":
            return agent
        if model is User:
            return user
        return None

    db.get.side_effect = get_model
    loop_result = SimpleNamespace(
        assistant=None,
        text="final",
        tool_context={"agent_name": "Writer", "summary": "ok"},
    )

    with patch(
        "app.services.workflows.nodes.tool.execute_tool_by_name", new_callable=AsyncMock
    ) as tool_call:
        tool_call.return_value = {"status": "succeeded", "text": "上游设计方案"}
        with patch(
            "app.services.workflows.nodes.agent.run_agent_function_call_loop",
            new_callable=AsyncMock,
        ) as call_loop:
            call_loop.return_value = loop_result
            with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
                await WorkflowEngine(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    task=task,
                    workflow_run=run,
                    workflow=workflow,
                    prompt="生成方案",
                    channel="conversation:conv-1",
                    agents=[agent],
                ).run()

    prompt = call_loop.await_args.kwargs["prompt"]
    assert "上游设计方案" in prompt
    assert "当前节点输入映射" in prompt


@pytest.mark.asyncio
async def test_tool_node_uses_upstream_reference_as_arguments() -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "source",
                "type": "tool",
                "config": {
                    "tool_name": "source.tool",
                    "output": {"text": "{{output.result.text}}"},
                },
            },
            {
                "id": "target",
                "type": "tool",
                "config": {"tool_name": "target.tool", "input": {"query": "{{nodes.source.text}}"}},
            },
            {"id": "end", "type": "end"},
        ],
        "edges": [["start", "source"], ["source", "target"], ["target", "end"]],
    }
    db, conversation, user_message, task, run = _runtime(workflow)
    db.get.side_effect = lambda model, item_id: (
        SimpleNamespace(id="user-1") if model is User else None
    )
    calls: list[dict[str, Any]] = []

    async def execute_tool(*_: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["arguments"])
        if kwargs["tool_name"] == "source.tool":
            return {"status": "succeeded", "text": "上游参数"}
        return {"status": "succeeded", "echo": kwargs["arguments"]}

    with patch("app.services.workflows.nodes.tool.execute_tool_by_name", side_effect=execute_tool):
        with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
            result = await WorkflowEngine(
                db,
                conversation=conversation,
                user_message=user_message,
                task=task,
                workflow_run=run,
                workflow=workflow,
                prompt="查一下",
                channel="conversation:conv-1",
                agents=[],
            ).run()

    assert calls[1]["query"] == "上游参数"
    assert result.outputs["target"]["arguments"]["query"] == "上游参数"


class FlakyExecutor(WorkflowNodeExecutor):
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, node: Any, context: Any) -> NodeExecutionResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary")
        return NodeExecutionResult(output={"ok": True}, retries=1)


class FailingExecutor(WorkflowNodeExecutor):
    async def execute(self, node: Any, context: Any) -> NodeExecutionResult:
        if node.id == "fail":
            return NodeExecutionResult(status="failed", output={"error": "boom"})
        return NodeExecutionResult(output={"ok": node.id})


class SlowParallelExecutor(WorkflowNodeExecutor):
    def __init__(self) -> None:
        self.started: list[str] = []
        self.events: list[tuple[str, str]] = []

    async def execute(self, node: Any, context: Any) -> NodeExecutionResult:
        if node.id in {"a", "b"}:
            self.started.append(node.id)
            self.events.append(("start", node.id))
            await asyncio.sleep(0.05)
            self.events.append(("finish", node.id))
        return NodeExecutionResult(output={"node": node.id})


@pytest.mark.asyncio
async def test_engine_retry_and_cancel_paths() -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "tool", "type": "tool", "config": {"retry": 1, "tool_name": "api.test"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [["start", "tool"], ["tool", "end"]],
    }
    db, conversation, user_message, task, run = _runtime(workflow)
    flaky = FlakyExecutor()

    with patch(
        "app.services.workflows.engine.get_executor",
        side_effect=lambda node_type: flaky if node_type == "tool" else WorkflowNodeExecutor(),
    ):
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


@pytest.mark.asyncio
async def test_engine_marks_failed_node_and_skips_downstream_dependencies() -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "fail", "type": "tool", "config": {"tool_name": "bad.tool"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [["start", "fail"], ["fail", "end"]],
    }
    db, conversation, user_message, task, run = _runtime(workflow)

    with patch("app.services.workflows.engine.get_executor", return_value=FailingExecutor()):
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

    states = {state["id"]: state for state in run.node_states}
    assert run.status == "failed"
    assert states["fail"]["status"] == "failed"
    assert states["fail"]["error"] == "boom"
    assert states["end"]["status"] == "skipped"
    assert result.outputs["fail"]["error"] == "boom"


@pytest.mark.asyncio
async def test_engine_runs_parallel_nodes_with_isolated_sessions() -> None:
    workflow = {
        "mode": "all_agents_independent",
        "output_mode": "independent_messages",
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "a", "type": "tool", "config": {"tool_name": "api.test"}},
            {"id": "b", "type": "tool", "config": {"tool_name": "db.inspect"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [["start", "a"], ["start", "b"], ["a", "end"], ["b", "end"]],
    }
    db, conversation, user_message, task, run = _runtime(workflow)
    executor = SlowParallelExecutor()

    def session_factory() -> Any:
        session = MagicMock()

        def get(model: Any, item_id: str) -> Any:
            mapping = {
                Conversation: conversation,
                Message: user_message,
                Task: task,
                WorkflowRun: run,
            }
            return mapping.get(model)

        session.get.side_effect = get
        return session

    with patch("app.services.workflows.engine.SessionLocal", side_effect=session_factory):
        with patch("app.services.workflows.engine.get_executor", return_value=executor):
            with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
                started_at = asyncio.get_running_loop().time()
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
                elapsed = asyncio.get_running_loop().time() - started_at

    first_finish_index = next(
        index for index, event in enumerate(executor.events) if event[0] == "finish"
    )
    started_before_first_finish = {
        node_id for event, node_id in executor.events[:first_finish_index] if event == "start"
    }
    assert set(executor.started) == {"a", "b"}
    assert started_before_first_finish == {"a", "b"}
    assert elapsed < 0.3
    assert result.outputs["a"]["node"] == "a"
    assert result.outputs["b"]["node"] == "b"


@pytest.mark.asyncio
async def test_aggregate_mode_agent_node_suppresses_chat_bubble() -> None:
    workflow = {**_workflow(), "output_mode": "aggregate"}
    db, conversation, user_message, task, run = _runtime(workflow)
    agent = SimpleNamespace(id="agent-1", name="Backend Worker", deleted_at=None)
    db.get.return_value = agent
    loop_result = SimpleNamespace(
        assistant=None,
        text="node only",
        tool_context={"agent_name": "Backend Worker", "summary": "node only"},
    )

    with patch(
        "app.services.workflows.nodes.agent.run_agent_function_call_loop", new_callable=AsyncMock
    ) as call_loop:
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

    assert call_loop.await_args.kwargs["emit_message"] is False
    assert result.outputs["a"]["assistant_message_id"] is None
    assert result.outputs["a"]["text"] == "node only"


@pytest.mark.asyncio
async def test_group_mention_runs_only_target_agent_and_skips_others() -> None:
    workflow = {
        "mode": "all_agents_independent",
        "output_mode": "independent_messages",
        "nodes": [
            {"id": "start", "type": "start"},
            {
                "id": "frontend",
                "type": "agent",
                "title": "Frontend Worker",
                "agent_id": "agent-frontend",
            },
            {
                "id": "daily",
                "type": "agent",
                "title": "Daily Chat Agent",
                "agent_id": "agent-daily",
            },
            {
                "id": "deploy",
                "type": "agent",
                "title": "Deploy Agent",
                "agent_id": "agent-deploy",
            },
            {"id": "end", "type": "end", "title": "End"},
        ],
        "edges": [
            ["start", "frontend"],
            ["start", "daily"],
            ["start", "deploy"],
            ["frontend", "end"],
            ["daily", "end"],
            ["deploy", "end"],
        ],
    }
    db, conversation, user_message, task, run = _runtime(workflow)
    conversation.chat_type = "group"
    agents = [
        SimpleNamespace(id="agent-frontend", name="Frontend Worker", deleted_at=None),
        SimpleNamespace(id="agent-daily", name="Daily Chat Agent", deleted_at=None),
        SimpleNamespace(id="agent-deploy", name="Deploy Agent", deleted_at=None),
    ]
    agent_by_id = {agent.id: agent for agent in agents}

    def get_model(model: Any, item_id: str) -> Any:
        if model is Agent:
            return agent_by_id.get(item_id)
        return None

    db.get.side_effect = get_model
    loop_result = SimpleNamespace(
        assistant=SimpleNamespace(id="assistant-daily"),
        text="daily only",
        tool_context={"agent_name": "Daily Chat Agent", "summary": "ok"},
    )

    with patch(
        "app.services.workflows.nodes.agent.run_agent_function_call_loop",
        new_callable=AsyncMock,
    ) as call_loop:
        call_loop.return_value = loop_result
        with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
            result = await WorkflowEngine(
                db,
                conversation=conversation,
                user_message=user_message,
                task=task,
                workflow_run=run,
                workflow=workflow,
                prompt="@Daily Chat Agent 你来回答一下",
                channel="conversation:conv-1",
                agents=agents,
            ).run()

    call_loop.assert_awaited_once()
    assert call_loop.await_args.kwargs["agent"].id == "agent-daily"
    assert len(result.agent_replies) == 1
    assert result.agent_replies[0]["agent_name"] == "Daily Chat Agent"
    states = {state["id"]: state for state in run.node_states}
    assert states["daily"]["status"] == "completed"
    assert states["frontend"]["status"] == "skipped"
    assert states["frontend"]["output"]["reason"] == "mention_target_filter"
    assert states["deploy"]["status"] == "skipped"
    assert states["deploy"]["output"]["reason"] == "mention_target_filter"


@pytest.mark.asyncio
async def test_end_node_aggregates_upstream_outputs() -> None:
    context = SimpleNamespace(
        outputs={
            "a": {"text": "frontend done"},
            "b": {"summary": "backend done"},
            "unrelated": {"text": "should not appear"},
        },
        node_input={
            "upstream": {
                "a": {"text": "frontend done"},
                "b": {"summary": "backend done"},
            }
        },
    )
    result = await EndNodeExecutor().execute(
        SimpleNamespace(id="end", type="end", config={}),
        context,
    )

    assert "frontend done" in result.output["summary"]
    assert "backend done" in result.output["summary"]
    assert "should not appear" not in result.output["summary"]


@pytest.mark.asyncio
async def test_tool_node_executes_real_tool_and_records_failure_status() -> None:
    workflow = {
        "nodes": [{"id": "tool", "type": "tool", "config": {"tool_name": "bad.tool"}}],
        "edges": [],
    }
    db, conversation, user_message, task, run = _runtime(workflow)
    context = SimpleNamespace(
        db=db,
        conversation=conversation,
        workflow_run=run,
        channel="conversation:conv-1",
        agents=[],
        outputs={},
        prompt="hello",
    )

    with patch(
        "app.services.workflows.nodes.tool.execute_tool_by_name", new_callable=AsyncMock
    ) as execute_tool:
        execute_tool.return_value = {"status": "failed", "output": "missing"}
        with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
            result = await ToolNodeExecutor().execute(
                WorkflowGraph.from_workflow(workflow).nodes[0], context
            )

    execute_tool.assert_awaited_once()
    assert result.status == "failed"
    assert result.output["result"]["output"] == "missing"


@pytest.mark.asyncio
async def test_artifact_node_uses_real_artifact_tool_executor() -> None:
    workflow = {
        "nodes": [
            {
                "id": "artifact",
                "type": "artifact",
                "title": "Deliverable",
                "config": {
                    "artifact_type": "pdf",
                    "name": "交付报告",
                    "content_model": {
                        "title": "交付报告",
                        "sections": [{"title": "摘要", "blocks": [{"type": "paragraph", "text": "{{input}}"}]}],
                    },
                },
            }
        ],
        "edges": [],
    }
    db, conversation, _user_message, _task, run = _runtime(workflow)
    db.get.side_effect = lambda model, item_id: SimpleNamespace(id="user-1") if model is User else None
    context = SimpleNamespace(
        db=db,
        conversation=conversation,
        workflow_run=run,
        channel="conversation:conv-1",
        outputs={},
        prompt="生成正式项目报告",
        node_input={"upstream_text": "上游分析结果"},
    )
    payload = {
        "status": "succeeded",
        "output": {
            "status": "succeeded",
            "artifact_id": "artifact-1",
            "artifact": {"id": "artifact-1", "name": "交付报告"},
            "preview_url": "/api/v1/artifacts/artifact-1/preview",
            "export_url": "/api/v1/artifacts/artifact-1/export?format=pdf",
            "format": "pdf",
            "filename": "交付报告.pdf",
            "media_type": "application/pdf",
        },
    }

    with patch(
        "app.services.workflows.nodes.artifact.execute_tool_by_name",
        new_callable=AsyncMock,
    ) as execute_tool:
        execute_tool.return_value = payload
        with patch("app.services.workflows.nodes.artifact.publish_tool_event", new_callable=AsyncMock):
            with patch("app.services.workflows.nodes.artifact.event_bus.publish", new_callable=AsyncMock) as publish:
                result = await ArtifactNodeExecutor().execute(
                    WorkflowGraph.from_workflow(workflow).nodes[0],
                    context,
                )

    execute_tool.assert_awaited_once()
    call = execute_tool.await_args.kwargs
    assert call["tool_name"] == "artifact.create_pdf"
    assert call["arguments"]["conversation_id"] == "conv-1"
    assert call["arguments"]["title"] == "交付报告"
    assert call["arguments"]["body"] == "上游分析结果"
    assert call["arguments"]["content_model"]["sections"][0]["blocks"][0]["text"] == "生成正式项目报告"
    assert result.status == "completed"
    assert result.output["artifact_id"] == "artifact-1"
    assert result.output["export_url"].endswith("format=pdf")
    assert any(call.args[1] == "artifact:created" for call in publish.await_args_list)
