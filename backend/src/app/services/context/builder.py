from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, Task, WorkflowRun
from app.services.context.compression import DEFAULT_CONTEXT_TOKENS, compact_json, fit_sections, join_sections
from app.services.context.group import build_group_member_context, format_group_message_content
from app.services.context.memory import (
    attachment_context,
    load_conversation_memory,
    maybe_capture_workspace_memory,
)
from app.services.context.runtime import build_runtime_context_view
from app.services.context.state import conversation_state, conversation_state_text
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
        group_context = build_group_member_context(self.db, conversation, agent)
        memory = load_conversation_memory(
            self.db,
            conversation,
            current_message_id=user_message.id,
            token_budget=max(1200, int(budget * 0.6)),
            speaker_identities=group_context.speaker_identities,
        )
        workspace = build_workspace_context(self.db, conversation, agent=agent)
        runtime = build_task_context(self.db, conversation, task=task, workflow_run=workflow_run)
        runtime_context = build_runtime_context_view(conversation, agent)
        attachments = attachment_context(user_message)
        context_sections = [
            ("群聊成员与身份规则", group_context.text),
            *runtime_context.to_sections(),
            ("会话摘要", memory.summary),
            ("conversation_state / conversation_variables", conversation_state_text(conversation)),
            ("recent_turns_digest：辅助省略指代线索，不作为事实主来源", memory.recent_turns_digest),
            ("任务/工具/工作流上下文", runtime.to_text()),
            ("当前工作区资源与长期记忆", workspace.to_text()),
            ("当前消息附件", attachments),
            ("工作流节点输入", compact_json(node_input or {}, max_chars=6000)),
        ]
        context_text = join_sections(fit_sections(context_sections, token_budget=max(1000, int(budget * 0.3))))
        messages: list[dict[str, Any]] = [{"role": "system", "content": _system_with_context_policy(system_prompt, context_text)}]
        messages.extend(memory.messages)
        latest_content = _latest_user_content(prompt, node_input)
        if group_context.speaker_identities:
            latest_content = format_group_message_content(
                sender_type=user_message.sender_type,
                sender_id=user_message.sender_id,
                sender_name=user_message.sender_name,
                text=latest_content,
                identities=group_context.speaker_identities,
            )
        messages.append({"role": "user", "content": latest_content})
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
                    "conversation_state": conversation_state(conversation),
                },
                "runtime_context": runtime_context.to_dict(),
                "group": {
                    "enabled": bool(group_context.text),
                    "member_context": group_context.text,
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


def _system_with_context_policy(system_prompt: str, context_text: str) -> str:
    context_block = f"\n\n## 上下文参考\n{context_text}" if context_text else ""
    return (
        f"{system_prompt}\n\n"
        "## 上下文范围说明\n"
        "你只能读取当前 conversation 的上下文：短期对话记忆、会话摘要、当前消息附件、工具/Skill/MCP 调用结果、工作流节点输出、当前工作区可见资源，以及用户明确授权写入的工作区长期记忆。\n"
        "你不能读取其他未授权会话、其他工作区或未提供给你的外部信息；如果用户追问其他会话内容，必须说明无法访问。\n"
        "普通对话历史会以真实 user/assistant role 消息提供；这些真实消息是事实主来源。\n"
        "recent_turns_digest 只用于辅助理解“继续、再加上、改一下、刚才那个”等省略表达，不能替代真实历史。\n"
        "conversation_state / conversation_variables 可用于读取当前会话内的结构化短期状态，如 last_math_result、last_topic、last_artifact_id、pending_reference。\n"
        "跨会话只能使用用户明确要求记住后写入当前工作区长期记忆的稳定事实、用户偏好、项目背景和长期目标。\n"
        "不要把一次性闲聊、敏感信息、临时计算过程写入长期记忆，也不要伪造长期记忆。\n"
        "Tool / Skill / MCP 的详细 schema 只通过 Function Calling tools 提供；普通上下文里只放当前 Agent 已授权能力摘要。\n"
        "图片附件如果没有视觉解析结果，只能说明当前未启用视觉解析，不能假装理解图片内容。\n"
        "工具结果必须作为事实来源，不要伪造工具执行、产物、下载链接或部署状态。\n"
        "受控沙箱工具不经过 shell：sandbox.run、terminal.start 的 command 只能是单条可执行命令，不能包含 cd、&&、;、|、>、< 或换行；需要切换目录时使用 workdir 参数，例如 command=\"python main.py\", workdir=\"backend\"。\n"
        "如果运行、测试、部署或终端工具失败，最终回复必须明确失败项和剩余风险，不能声称依赖已安装、服务已启动、测试通过或部署成功。"
        f"{context_block}"
    )


def _latest_user_content(prompt: str, node_input: dict[str, Any] | None) -> str:
    sections = [prompt]
    if node_input:
        sections.append(f"## 工作流节点输入\n{compact_json(node_input, max_chars=6000)}")
    return "\n\n".join(sections)


def _agent_budget(agent: Agent) -> int:
    config = agent.config if isinstance(agent.config, dict) else {}
    value = config.get("max_context_tokens") or config.get("context_window") or DEFAULT_CONTEXT_TOKENS
    try:
        return max(2000, min(int(value), 64_000))
    except (TypeError, ValueError):
        return DEFAULT_CONTEXT_TOKENS
