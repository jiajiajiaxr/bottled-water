from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, Task, WorkflowRun
from app.services.workflows.events import publish_node_event, publish_run_updated
from app.services.workflows.graph import Node, WorkflowGraph
from app.services.workflows.nodes import get_executor
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext
from app.services.workflows.runtime import (
    _set_workflow_node_state,
    _sync_workflow_run,
    append_run_event,
    mark_workflow_completed,
    set_edge_state,
)
from app.services.workflows.scheduler import WorkflowScheduler
from app.services.workflows.validator import validate_workflow_graph


@dataclass
class WorkflowEngineResult:
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    worker_contexts: list[dict[str, Any]] = field(default_factory=list)
    agent_replies: list[dict[str, str]] = field(default_factory=list)
    skipped_nodes: set[str] = field(default_factory=set)

    @property
    def tool_context(self) -> dict[str, Any]:
        return {
            "mode": "workflow_engine",
            "executions": [],
            "worker_contexts": self.worker_contexts,
            "summary": "workflow nodes executed",
            "node_outputs": self.outputs,
        }


class WorkflowEngine:
    def __init__(
        self,
        db: Session,
        *,
        conversation: Conversation,
        user_message: Message,
        task: Task,
        workflow_run: WorkflowRun,
        workflow: dict[str, Any],
        prompt: str,
        channel: str,
        agents: list[Agent],
    ) -> None:
        self.db = db
        self.conversation = conversation
        self.user_message = user_message
        self.task = task
        self.workflow_run = workflow_run
        self.workflow = workflow
        self.prompt = prompt
        self.channel = channel
        self.agents = agents
        self.graph = WorkflowGraph.from_workflow(workflow)
        self.scheduler = WorkflowScheduler(self.graph)
        self.result = WorkflowEngineResult()

    async def run(self) -> WorkflowEngineResult:
        validation = validate_workflow_graph(self.workflow, agents=self.agents)
        if not validation.ok:
            raise ValueError("; ".join(validation.errors))
        append_run_event(self.workflow_run, "run.engine_started", {"warnings": validation.warnings})
        self.db.commit()
        await publish_run_updated(self.channel, self.workflow_run)

        for level in self.scheduler.parallel_levels():
            runnable = [node for node in level if node.id not in self.result.skipped_nodes]
            if not runnable:
                continue
            if len(runnable) > 1 and self.workflow.get("mode") == "all_agents_independent":
                # SQLAlchemy sessions are not shared across concurrent workers in
                # this code path yet; execute the batch in graph order while
                # preserving the scheduler's parallel level semantics in state.
                for node in runnable:
                    await self._run_node(node)
            else:
                for node in runnable:
                    await self._run_node(node)
            if self.workflow_run.status == "cancelled":
                break

        if self.workflow_run.status != "cancelled":
            mark_workflow_completed(self.conversation, self.workflow_run)
            self.db.commit()
            await publish_run_updated(self.channel, self.workflow_run)
        return self.result

    async def _run_node(self, node: Node) -> None:
        if self.workflow_run.status == "cancelled":
            return
        retry_limit = max(0, min(int(node.config.get("retry") or node.config.get("retry_count") or 0), 3))
        attempt = 0
        while True:
            try:
                await self._mark_node(node, "running", 20, message=f"{node.title} running")
                execution = await get_executor(node.type).execute(node, self._context())
                await self._complete_node(node, execution)
                return
            except asyncio.CancelledError:
                self.workflow_run.status = "cancelled"
                append_run_event(self.workflow_run, "run.cancelled", {"node_id": node.id})
                _sync_workflow_run(self.conversation, self.workflow_run)
                self.db.commit()
                await publish_run_updated(self.channel, self.workflow_run, node_id=node.id)
                raise
            except Exception as exc:
                attempt += 1
                if attempt <= retry_limit:
                    append_run_event(self.workflow_run, "node.retry", {"node_id": node.id, "attempt": attempt})
                    self.db.commit()
                    continue
                await self._mark_node(
                    node,
                    "failed",
                    100,
                    output={"error": str(exc), "attempts": attempt},
                    message=f"{node.title} failed",
                )
                raise

    def _context(self) -> WorkflowExecutionContext:
        return WorkflowExecutionContext(
            db=self.db,
            conversation=self.conversation,
            user_message=self.user_message,
            task=self.task,
            workflow_run=self.workflow_run,
            prompt=self.prompt,
            channel=self.channel,
            agents=self.agents,
            outputs=self.result.outputs,
            cancelled=self.workflow_run.status == "cancelled",
        )

    async def _mark_node(
        self,
        node: Node,
        status: str,
        progress: int,
        output: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> None:
        _set_workflow_node_state(
            self.workflow_run,
            node.id,
            status=status,
            progress=progress,
            output=output,
            message=message,
        )
        append_run_event(self.workflow_run, f"node.{status}", {"node_id": node.id})
        _sync_workflow_run(self.conversation, self.workflow_run)
        self.db.commit()
        await publish_node_event(self.channel, self.workflow_run, node.id, status, {"message": message} if message else None)

    async def _complete_node(self, node: Node, execution: NodeExecutionResult) -> None:
        self.result.outputs[node.id] = execution.output
        if node.type in {"agent", "review"}:
            self.result.worker_contexts.append(
                {
                    "subtask_id": node.id,
                    "subtask_title": node.title,
                    "agent_id": node.agent_id,
                    "agent_name": execution.output.get("agent_name"),
                    "context": execution.output,
                }
            )
            if execution.output.get("text"):
                self.result.agent_replies.append(
                    {
                        "agent_id": str(node.agent_id or ""),
                        "agent_name": str(execution.output.get("agent_name") or node.title),
                        "text": str(execution.output.get("text"))[:1000],
                    }
                )
        if execution.branch:
            for skipped in self.scheduler.skip_branch_targets(node.id, execution.branch):
                self.result.skipped_nodes.add(skipped)
                await self._mark_node(
                    self.graph.node_by_id[skipped],
                    "skipped",
                    100,
                    output={"reason": "condition_branch_not_matched", "matched_branch": execution.branch},
                    message="Skipped by condition",
                )
        for edge in self.graph.outgoing.get(node.id, []):
            set_edge_state(
                self.workflow_run,
                edge.source,
                edge.target,
                "skipped" if edge.target in self.result.skipped_nodes else "ready",
            )
        await self._mark_node(
            node,
            execution.status,
            100,
            output=execution.output,
            message=execution.message,
        )
