from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Agent, Conversation, Message, Task, WorkflowRun
from app.services.context.task import build_task_context
from app.services.context.workspace import build_workspace_context
from app.services.workflows.events import publish_node_event, publish_run_updated
from app.services.workflows.graph import Node, WorkflowGraph
from app.services.workflows.io import resolve_node_input, resolve_node_output
from app.services.workflows.mentions import MentionTargetFilter, resolve_mention_target_filter
from app.services.workflows.nodes import get_executor
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext
from app.services.workflows.runtime import (
    _set_workflow_node_state,
    _sync_workflow_run,
    append_run_event,
    mark_workflow_completed,
    mutate_workflow_run_locked,
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
        settings = workflow.get("settings") if isinstance(workflow.get("settings"), dict) else {}
        self.output_mode = str(
            workflow.get("output_mode") or settings.get("output_mode") or "independent_messages"
        )
        self.mention_filter = self._resolve_mention_filter()

    async def run(self) -> WorkflowEngineResult:
        validation = validate_workflow_graph(self.workflow, agents=self.agents)
        if not validation.ok:
            await self._fail_run(None, ValueError("; ".join(validation.errors)))
            return self.result
        append_run_event(self.workflow_run, "run.engine_started", {"warnings": validation.warnings})
        self.db.commit()
        await publish_run_updated(self.channel, self.workflow_run)
        await self._apply_mention_target_filter()

        for level in self.scheduler.parallel_levels():
            runnable = [node for node in level if node.id not in self.result.skipped_nodes]
            if not runnable:
                continue
            if len(runnable) > 1:
                batch = await asyncio.gather(
                    *[
                        self._run_node_in_isolated_session(node, dict(self.result.outputs))
                        for node in runnable
                    ]
                )
                failed_node: Node | None = None
                for node, ok, child_result in batch:
                    self.result.outputs.update(child_result.outputs)
                    self.result.worker_contexts.extend(child_result.worker_contexts)
                    self.result.agent_replies.extend(child_result.agent_replies)
                    self.result.skipped_nodes.update(child_result.skipped_nodes)
                    if not ok and self.workflow_run.status != "cancelled" and failed_node is None:
                        failed_node = node
                self.db.refresh(self.workflow_run)
                if failed_node:
                    await self._fail_run(failed_node)
                    return self.result
            else:
                for node in runnable:
                    if self.workflow_run.status == "cancelled":
                        break
                    if not await self._run_node(node) and self.workflow_run.status != "cancelled":
                        await self._fail_run(node)
                        return self.result
            if self.workflow_run.status == "cancelled":
                break

        if self.workflow_run.status != "cancelled":
            mark_workflow_completed(self.conversation, self.workflow_run)
            self.db.commit()
            await publish_run_updated(self.channel, self.workflow_run)
        return self.result

    async def _run_node_in_isolated_session(
        self,
        node: Node,
        upstream_outputs: dict[str, dict[str, Any]],
    ) -> tuple[Node, bool, WorkflowEngineResult]:
        db = SessionLocal()
        try:
            conversation = db.get(Conversation, self.conversation.id)
            user_message = (
                db.get(Message, self.user_message.id)
                if getattr(self.user_message, "id", None)
                else self.user_message
            )
            task = db.get(Task, self.task.id)
            workflow_run = db.get(WorkflowRun, self.workflow_run.id)
            agents = [
                agent
                for agent_id in [agent.id for agent in self.agents]
                if (agent := db.get(Agent, agent_id)) is not None
            ]
            if not conversation or not user_message or not task or not workflow_run:
                return node, False, WorkflowEngineResult()
            isolated = WorkflowEngine(
                db,
                conversation=conversation,
                user_message=user_message,
                task=task,
                workflow_run=workflow_run,
                workflow=self.workflow,
                prompt=self.prompt,
                channel=self.channel,
                agents=agents,
            )
            isolated.result.outputs.update(upstream_outputs)
            ok = await isolated._run_node(node)
            return node, ok, isolated.result
        finally:
            db.close()

    def _resolve_mention_filter(self) -> MentionTargetFilter | None:
        if getattr(self.conversation, "chat_type", None) != "group":
            return None
        mention_filter = resolve_mention_target_filter(self.prompt, self.agents)
        if not mention_filter:
            return None
        has_target_node = any(
            node.type in {"agent", "review"} and node.agent_id in mention_filter.agent_ids
            for node in self.graph.nodes
        )
        return mention_filter if has_target_node else None

    async def _apply_mention_target_filter(self) -> None:
        if not self.mention_filter:
            return
        for node in self.graph.nodes:
            if node.type not in {"agent", "review"}:
                continue
            if node.agent_id in self.mention_filter.agent_ids:
                continue
            output = {
                "reason": "mention_target_filter",
                "target_agent_ids": sorted(self.mention_filter.agent_ids),
                "target_agent_names": self.mention_filter.agent_names,
            }
            self.result.skipped_nodes.add(node.id)
            self.result.outputs[node.id] = output
            edge_updates = [
                (edge.source, edge.target, "skipped")
                for edge in [*self.graph.incoming.get(node.id, []), *self.graph.outgoing.get(node.id, [])]
            ]
            await self._mark_node(
                node,
                "skipped",
                100,
                output=output,
                message="Skipped by @Agent target",
                edge_updates=edge_updates,
            )

    async def _run_node(self, node: Node) -> bool:
        if self.workflow_run.status == "cancelled":
            return False
        retry_limit = self._retry_limit(node)
        failure_strategy = self._failure_strategy(node)
        attempt = 0
        while True:
            try:
                node_input = self._node_input(node)
                await self._mark_node(
                    node,
                    "running",
                    20,
                    input_data=node_input,
                    message=f"{node.title} running",
                )
                execution = await get_executor(node.type).execute(node, self._context(node_input))
                execution.output = resolve_node_output(
                    node=node,
                    prompt=self.prompt,
                    outputs=self.result.outputs,
                    node_input=node_input,
                    raw_output=execution.output,
                    graph=self.graph,
                )
                if execution.status in {"failed", "error"} and attempt < retry_limit:
                    attempt += 1
                    await self._mark_retry(node, attempt, retry_limit, str(execution.output.get("error") or "node failed"))
                    continue
                if execution.status in {"failed", "error"} and failure_strategy == "skip":
                    execution = NodeExecutionResult(
                        status="skipped",
                        output={
                            **(execution.output or {}),
                            "reason": "failure_strategy_skip",
                            "failed_status": execution.status,
                        },
                        branch=execution.branch,
                        message=execution.message or f"{node.title} skipped after failure",
                        retries=attempt,
                    )
                execution.retries = max(execution.retries, attempt)
                await self._complete_node(node, execution)
                return execution.status not in {"failed", "error"}
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
                    await self._mark_retry(node, attempt, retry_limit, str(exc))
                    continue
                if failure_strategy == "skip":
                    await self._mark_node(
                        node,
                        "skipped",
                        100,
                        output={
                            "reason": "failure_strategy_skip",
                            "error": str(exc),
                            "attempts": attempt,
                        },
                        retry_count=attempt,
                        message=f"{node.title} skipped after failure",
                        edge_updates=[
                            *[
                                (edge.source, edge.target, "skipped")
                                for edge in self.graph.incoming.get(node.id, [])
                            ],
                            *[
                                (edge.source, edge.target, "ready")
                                for edge in self.graph.outgoing.get(node.id, [])
                            ],
                        ],
                    )
                    self.result.outputs[node.id] = {
                        "reason": "failure_strategy_skip",
                        "error": str(exc),
                        "attempts": attempt,
                    }
                    return True
                await self._mark_node(
                    node,
                    "failed",
                    100,
                    output={"error": str(exc), "attempts": attempt},
                    error=str(exc),
                    retry_count=attempt,
                    message=f"{node.title} failed",
                )
                return False

    def _retry_limit(self, node: Node) -> int:
        raw = node.config.get("retry")
        if raw is None:
            raw = node.config.get("retry_count")
        if raw is None and self._failure_strategy(node) == "retry":
            raw = 1
        try:
            return max(0, min(int(raw or 0), 3))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _failure_strategy(node: Node) -> str:
        value = str(node.config.get("failure_strategy") or node.config.get("on_failure") or "stop")
        value = value.lower().strip()
        return value if value in {"stop", "skip", "retry"} else "stop"

    async def _mark_retry(self, node: Node, attempt: int, retry_limit: int, error: str) -> None:
        await self._mark_node(
            node,
            "running",
            20,
            output={"last_error": error},
            retry_count=attempt,
            message=f"{node.title} retrying ({attempt}/{retry_limit})",
        )
        append_run_event(
            self.workflow_run,
            "node.retry",
            {"node_id": node.id, "attempt": attempt, "retry_limit": retry_limit, "error": error},
        )
        self.db.commit()

    def _context(self, node_input: dict[str, Any]) -> WorkflowExecutionContext:
        return WorkflowExecutionContext(
            db=self.db,
            conversation=self.conversation,
            user_message=self.user_message,
            task=self.task,
            workflow_run=self.workflow_run,
            prompt=self.prompt,
            channel=self.channel,
            agents=self.agents,
            output_mode=self.output_mode,
            outputs=self.result.outputs,
            node_input=node_input,
            cancelled=self.workflow_run.status == "cancelled",
        )

    async def _mark_node(
        self,
        node: Node,
        status: str,
        progress: int,
        input_data: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        message: str | None = None,
        edge_updates: list[tuple[str, str, str]] | None = None,
        retry_count: int | None = None,
    ) -> None:
        def _mutate(run: WorkflowRun) -> None:
            if status == "running":
                for edge in self.graph.incoming.get(node.id, []):
                    set_edge_state(run, edge.source, edge.target, "running")
            for source, target, edge_status in edge_updates or []:
                set_edge_state(run, source, target, edge_status)
            _set_workflow_node_state(
                run,
                node.id,
                status=status,
                progress=progress,
                input_data=input_data,
                output=output,
                error=error,
                message=message,
                retry_count=retry_count,
            )
            append_run_event(
                run,
                f"node.{status}",
                {
                    "node_id": node.id,
                    **({"error": error} if error else {}),
                    **({"retry_count": retry_count} if retry_count is not None else {}),
                },
            )

        await mutate_workflow_run_locked(self.db, self.conversation, self.workflow_run, _mutate)
        await publish_node_event(
            self.channel,
            self.workflow_run,
            node.id,
            status,
            {"message": message, **({"error": error} if error else {})}
            if message or error
            else None,
        )

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
                    output={
                        "reason": "condition_branch_not_matched",
                        "matched_branch": execution.branch,
                    },
                    message="Skipped by condition",
                )
        edge_updates = [
            (edge.source, edge.target, execution.status)
            for edge in self.graph.incoming.get(node.id, [])
        ]
        edge_updates.extend(
            (
                edge.source,
                edge.target,
                "skipped" if edge.target in self.result.skipped_nodes else "ready",
            )
            for edge in self.graph.outgoing.get(node.id, [])
        )
        await self._mark_node(
            node,
            execution.status,
            100,
            output=execution.output,
            error=execution.output.get("error")
            if execution.status in {"failed", "error"}
            else None,
            message=execution.message,
            edge_updates=edge_updates,
            retry_count=execution.retries,
        )

    def _node_input(self, node: Node) -> dict[str, Any]:
        node_input = resolve_node_input(
            node=node,
            graph=self.graph,
            prompt=self.prompt,
            outputs=self.result.outputs,
        )
        workspace = build_workspace_context(self.db, self.conversation)
        runtime = build_task_context(
            self.db,
            self.conversation,
            task=self.task,
            workflow_run=self.workflow_run,
        )
        node_input.setdefault("workspace", workspace.to_dict())
        node_input.setdefault("workspace_text", workspace.to_text())
        node_input.setdefault("runtime", runtime.to_dict())
        return node_input

    async def _fail_run(self, node: Node | None, error: Exception | None = None) -> None:
        error_text = str(error) if error else None
        if node:
            for skipped_id in self.graph.descendants(node.id):
                if skipped_id in self.result.outputs:
                    continue
                self.result.skipped_nodes.add(skipped_id)
                await self._mark_node(
                    self.graph.node_by_id[skipped_id],
                    "skipped",
                    100,
                    output={"reason": "dependency_failed", "failed_dependency": node.id},
                    message="Skipped because an upstream node failed",
                )
        self.workflow_run.status = "failed"
        append_run_event(
            self.workflow_run,
            "run.failed",
            {"node_id": node.id if node else None, **({"error": error_text} if error_text else {})},
        )
        mark_workflow_completed(self.conversation, self.workflow_run, status="failed")
        self.db.commit()
        await publish_run_updated(
            self.channel, self.workflow_run, node_id=node.id if node else None
        )
