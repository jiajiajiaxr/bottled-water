from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, Task, WorkflowRun
from app.services.context.compression import DEFAULT_CONTEXT_TOKENS, compact_json, fit_sections, join_sections
from app.services.context.memory import attachment_context, load_conversation_memory
from app.services.context.task import build_task_context, summarize_tool_result
from app.services.context.workspace import build_workspace_context


@dataclass
class AgentContextBundle:
    messages: list[dict[str, Any]]
    sections: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build_agent_messages(
        self,
        *,
        conversation: Conversation,
        user_message: Message,
        agent: Agent,
        system_prompt: str,
        prompt: str,
        mode: str,
        task: Task | None = None,
        workflow_run: WorkflowRun | None = None,
        workflow_node_id: str | None = None,
        node_input: dict[str, Any] | None = None,
        token_budget: int | None = None,
    ) -> AgentContextBundle:
        budget = token_budget or _agent_budget(agent)
        memory = load_conversation_memory(
            self.db,
            conversation,
            current_message_id=user_message.id,
            token_budget=max(1000, budget // 4),
        )
        workspace = build_workspace_context(self.db, conversation)
        runtime = build_task_context(self.db, conversation, task=task, workflow_run=workflow_run)
        attachments = attachment_context(user_message)
        sections = [
            ("当前用户输入", prompt),
            ("当前消息附件", attachments),
            ("工作流节点输入", compact_json(node_input or {}, max_chars=6000)),
            ("当前工作区资源", workspace.to_text()),
            ("任务与运行态上下文", runtime.to_text()),
        ]
        context_text = join_sections(fit_sections(sections, token_budget=max(1000, budget // 2)))
        system = (
            f"{system_prompt}\n\n"
            "## 上下文范围说明\n"
            "你只能读取当前 conversation 的上下文：最近消息、已持久化摘要、当前消息附件、工具/Skill/MCP 调用结果、工作流节点输出、当前工作区中可见的文件/产物/工具/Skill/MCP 资源。\n"
            "你不能读取其他未授权会话、其他工作区或未提供给你的外部信息；如果用户追问其它会话内容，必须说明无法访问。\n"
            "当用户问“你记得/能读取之前对话吗”时，请基于当前会话历史如实回答，并尽量引用最近一条相关用户消息。\n"
            "图片附件如果没有视觉解析结果，只能说明当前未启用视觉解析，不能假装理解图片内容。\n"
            "工具结果必须作为事实来源，不要伪造工具执行、产物、下载链接或部署状态。"
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if memory.summary:
            messages.append({"role": "system", "content": f"## 当前会话摘要\n{memory.summary}"})
        messages.extend(memory.messages)
        messages.append({"role": "user", "content": context_text or prompt})
        return AgentContextBundle(
            messages=messages,
            sections={
                "mode": mode,
                "workspace": workspace.to_dict(),
                "runtime": runtime.to_dict(),
                "node_input": node_input or {},
                "workflow_node_id": workflow_node_id,
            },
            diagnostics={"budget": budget, "memory": memory.diagnostics},
        )

    def tool_result_message(
        self,
        *,
        conversation: Conversation,
        tool_call_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": summarize_tool_result(self.db, conversation, result),
        }


def _agent_budget(agent: Agent) -> int:
    config = agent.config if isinstance(agent.config, dict) else {}
    value = config.get("max_context_tokens") or config.get("context_window") or DEFAULT_CONTEXT_TOKENS
    try:
        return max(2000, min(int(value), 64_000))
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_TOKENS
