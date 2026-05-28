from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, Task, WorkflowRun
from app.services.context.compression import DEFAULT_CONTEXT_TOKENS, compact_json, fit_sections, join_sections
from app.services.context.memory import (
    attachment_context,
    load_conversation_memory,
    maybe_capture_workspace_memory,
)
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
        maybe_capture_workspace_memory(self.db, conversation, user_message)
        memory = load_conversation_memory(
            self.db,
            conversation,
            current_message_id=user_message.id,
            token_budget=max(1000, budget // 4),
        )
        workspace = build_workspace_context(self.db, conversation, agent=agent)
        runtime = build_task_context(self.db, conversation, task=task, workflow_run=workflow_run)
        attachments = attachment_context(user_message)
        context_sections = [
            ("会话摘要", memory.summary),
            ("recent_turns_digest：最近多轮关键事实与省略指代", memory.recent_turns_digest),
            ("短期记忆：最近原文对话", memory.recent_messages_text),
            ("任务/工具/工作流上下文", runtime.to_text()),
            ("当前工作区资源与长期记忆", workspace.to_text()),
            ("当前消息附件", attachments),
            ("工作流节点输入", compact_json(node_input or {}, max_chars=6000)),
        ]
        context_text = join_sections(fit_sections(context_sections, token_budget=max(1000, budget // 2)))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _system_with_context_policy(system_prompt)},
            {"role": "system", "content": context_text},
            {"role": "user", "content": f"## 最新用户输入\n{prompt}"},
        ]
        return AgentContextBundle(
            messages=messages,
            sections={
                "mode": mode,
                "workspace": workspace.to_dict(),
                "runtime": runtime.to_dict(),
                "memory": {
                    "summary": memory.summary,
                    "recent_turns_digest": memory.recent_turns_digest,
                    "recent_messages_text": memory.recent_messages_text,
                },
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


def _system_with_context_policy(system_prompt: str) -> str:
    return (
        f"{system_prompt}\n\n"
        "## 上下文范围说明\n"
        "你只能读取当前 conversation 的上下文：短期对话记忆、会话摘要、当前消息附件、工具/Skill/MCP 调用结果、工作流节点输出、当前工作区可见资源和已授权的工作区长期记忆。\n"
        "你不能读取其他未授权会话、其他工作区或未提供给你的外部信息；如果用户追问其它会话内容，必须说明无法访问。\n"
        "当用户说“继续、再加上、改一下、刚才那个”等省略表达时，优先使用当前会话短期记忆和 recent_turns_digest 消解指代。\n"
        "跨会话只能使用已写入当前工作区长期记忆的稳定事实、用户偏好、项目背景和长期目标。\n"
        "不要把一次性闲聊、敏感信息、临时计算过程写入长期记忆，也不要伪造长期记忆。\n"
        "图片附件如果没有视觉解析结果，只能说明当前未启用视觉解析，不能假装理解图片内容。\n"
        "工具结果必须作为事实来源，不要伪造工具执行、产物、下载链接或部署状态。"
    )


def _agent_budget(agent: Agent) -> int:
    config = agent.config if isinstance(agent.config, dict) else {}
    value = config.get("max_context_tokens") or config.get("context_window") or DEFAULT_CONTEXT_TOKENS
    try:
        return max(2000, min(int(value), 64_000))
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_TOKENS
