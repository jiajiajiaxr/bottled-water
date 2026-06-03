"""
Agent 执行循环

负责单个 Agent 的单轮执行：
- 构建上下文（私有栈 + Blackboard 视图）
- 调用 LLM（支持工具调用）
- 处理工具调用（多轮）
- 状态自报告
"""

import re
import json
import uuid
from typing import Dict, Any, Optional, List

from model_provider.core.interfaces import BaseModelProvider, ChatMessage, ChatResponse

from common.logger import get_logger
from ..core.types import AgentConfig, AgentReport, AgentState, AgentWill, ToolCall, ToolResult
from ..core.interfaces import ToolExecutor
from ..context.agent_ctx import AgentContext

logger = get_logger(__name__)


class AgentLoop:
    """Agent 执行循环

    支持两种模式：
    1. 传统模式：run() 一次性执行完所有步骤
    2. 步进模式：step() 每次执行一步，支持外部干预
    """

    MAX_TOOL_ROUNDS = 10  # 最大工具调用轮数，防止无限循环

    def __init__(
        self,
        agent_config: AgentConfig,
        model_provider: BaseModelProvider,
        use_streaming: bool = False,
    ):
        self.agent = agent_config
        self.model = model_provider
        self.use_streaming = use_streaming
        self._state = AgentState.IDLE
        self._step_data: Dict[str, Any] = {}

    @property
    def state(self) -> AgentState:
        """当前状态（只读）"""
        return self._state

    def _set_state(self, new_state: AgentState):
        """设置状态并记录日志"""
        if self._state != new_state:
            logger.debug(
                "Agent 状态变更",
                agent_id=self.agent.id,
                old=self._state.value,
                new=new_state.value,
            )
            self._state = new_state

    async def run(
        self,
        task: str,
        blackboard_view: dict,
        tool_executor: Optional[ToolExecutor] = None,
        agent_ctx: Optional[AgentContext] = None,
        emit_event=None,
    ) -> Dict[str, Any]:
        """
        执行 Agent 单轮任务。

        流程：
        1. 注入 AgentContext 历史帧到消息列表
        2. 构建用户提示词
        3. 调用 LLM（带工具列表）
        4. 如果 LLM 返回 tool_calls，执行工具并回传结果
        5. 重复步骤 3-4 直到 LLM 不再调用工具或达到上限
        6. 解析最终回复，提取成果和状态报告
        7. 将本轮对话归档回 AgentContext

        Args:
            emit_event: 可选的事件发射回调，签名 async fn(event: Event) -> None

        Returns:
            {"work_product": str, "status_report": AgentReport}
        """
        from ..core.types import Event

        agent_source = f"agent:{self.agent.id}"

        async def _emit(event_type: str, payload: dict, channel: str = "internal"):
            if emit_event:
                await emit_event(
                    Event(
                        type=event_type,
                        payload=payload,
                        source=agent_source,
                        channel=channel,
                    )
                )

        logger.info("Agent 执行开始", agent_id=self.agent.id, task=task[:50])
        self._set_state(AgentState.RUNNING)
        await _emit("agent.thinking", {"task": task, "agent_id": self.agent.id})

        try:
            result = await self._execute_loop(
                task, blackboard_view, tool_executor, agent_ctx, _emit
            )
            self._set_state(AgentState.COMPLETED)
            return result
        except Exception:
            self._set_state(AgentState.FAILED)
            raise

    async def _execute_loop(
        self,
        task: str,
        blackboard_view: dict,
        tool_executor: Optional[ToolExecutor],
        agent_ctx: Optional[AgentContext],
        _emit,
    ) -> Dict[str, Any]:
        """内部执行循环（被 run() 和步进模式共用）"""
        # 虚拟工具智能体：跳过 LLM，直接执行工具
        if self.agent.system_prompt == "" and self.agent.role.endswith("_executor"):
            return await self._execute_virtual_agent(task, tool_executor, _emit)

        # 构建系统提示词
        system_prompt = self.agent.system_prompt

        # 构建消息列表
        messages: List[ChatMessage] = []

        # 注入 AgentContext 历史帧（如果提供），先做 Token 截断
        if agent_ctx:
            agent_ctx.trim(max_tokens=4000)
            for frame in agent_ctx.frames:
                if frame.frame_type == "thought":
                    messages.append(ChatMessage(role="assistant", content=str(frame.content)))
                elif frame.frame_type == "tool_call":
                    # tool_call 帧存储为 dict，尝试恢复
                    tc = frame.content
                    if isinstance(tc, dict):
                        messages.append(
                            ChatMessage(
                                role="assistant",
                                content="",
                                tool_calls=[tc],
                            )
                        )
                elif frame.frame_type == "tool_result":
                    # tool_result 帧存储为 dict 或字符串
                    tr = frame.content
                    if isinstance(tr, dict):
                        messages.append(
                            ChatMessage(
                                role="tool",
                                content=str(tr.get("result", "")),
                                name=tr.get("tool", "unknown"),
                            )
                        )
                    else:
                        messages.append(ChatMessage(role="tool", content=str(tr)))

        # 构建用户提示词
        user_prompt = self._build_prompt(task, blackboard_view)
        messages.append(ChatMessage(role="user", content=user_prompt))

        # 获取可用工具（按 AgentConfig.tools 过滤）
        tools = []
        if tool_executor:
            all_tools = await tool_executor.list_tools()
            if self.agent.tools:
                allowed = set(self.agent.tools)
                tools = [t for t in all_tools if t.get("function", {}).get("name") in allowed]
            else:
                tools = all_tools
            logger.debug("Agent 可用工具", agent_id=self.agent.id, tool_count=len(tools))

        # 工具调用循环
        tool_results: List[Dict[str, Any]] = []
        tool_events: List[Dict[str, Any]] = []
        tool_round = 0

        while tool_round < self.MAX_TOOL_ROUNDS:
            tool_round += 1

            try:
                if self.use_streaming:
                    response = await self._chat_streaming(
                        messages=messages,
                        system_prompt=system_prompt,
                        tools=tools if tools else None,
                        _emit=_emit,
                    )
                else:
                    response = await self.model.chat(
                        messages=messages,
                        system_prompt=system_prompt,
                        tools=tools if tools else None,
                    )
            except Exception as e:
                logger.error("Agent LLM 调用失败", agent_id=self.agent.id, error=str(e))
                raise

            content = response.content or ""
            tool_calls = response.tool_calls

            # 如果没有工具调用，说明 Agent 已完成本轮工作
            if not tool_calls:
                logger.info("Agent 无工具调用", agent_id=self.agent.id)
                messages.append(ChatMessage(role="assistant", content=content))

                break

            # 处理工具调用
            logger.info(
                "Agent 工具调用",
                agent_id=self.agent.id,
                tool_count=len(tool_calls),
                round=tool_round,
            )
            await _emit(
                "agent.tool_call",
                {
                    "agent_id": self.agent.id,
                    "tool_count": len(tool_calls),
                    "tools": [tc.get("function", {}).get("name", "unknown") for tc in tool_calls],
                },
            )

            # 将 assistant 消息（含 tool_calls）加入消息列表
            assistant_msg = ChatMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
            )
            messages.append(assistant_msg)

            # 执行每个工具调用
            for tc in tool_calls:
                if not tool_executor:
                    break

                tool_call, err = ToolCall.new(tc)

                if err:
                    logger.error("工具参数解析失败", tool=tool_call.tool_name, error=str(err))

                    result = ToolResult(
                        call_id=tool_call.call_id,
                        success=False,
                        result=None,
                        error=f"参数解析失败: {err}",
                    )

                else:
                    try:
                        logger.info(
                            "执行工具",
                            agent_id=self.agent.id,
                            tool=tool_call.tool_name,
                            call_id=tool_call.call_id,
                        )

                        # 执行工具
                        result = await tool_executor.execute(tool_call)

                        # 如果 result 已经是 ToolResult，直接返回
                        if not isinstance(result, ToolResult):
                            # 否则包装为 ToolResult
                            result = ToolResult(
                                call_id=tool_call.call_id,
                                success=True,
                                result=result,
                            )
                    except Exception as e:
                        logger.error("工具执行失败", tool=tool_call.tool_name, error=str(e))

                        result = ToolResult(
                            call_id=tool_call.call_id,
                            success=False,
                            result=None,
                            error=str(e),
                        )

                tool_name = tc.get("function", {}).get("name", "unknown")
                tool_results.append(
                    {
                        "tool": tool_name,
                        "success": result.success if isinstance(result, ToolResult) else True,
                        "result": result.result if isinstance(result, ToolResult) else result,
                    }
                )

                await _emit(
                    "agent.tool_result",
                    {
                        "agent_id": self.agent.id,
                        "tool": tool_name,
                        "success": result.success if isinstance(result, ToolResult) else True,
                    },
                )

                # 将工具结果加入消息列表
                tool_msg = ChatMessage(
                    role="tool",
                    content=str(result.result if isinstance(result, ToolResult) else result),
                    name=tool_name,
                )
                messages.append(tool_msg)

            tool_events.append(
                {
                    "agent_id": self.agent.id,
                    "round": tool_round,
                    "results": tool_results[-len(tool_calls) :],
                }
            )

        # 如果达到工具调用上限
        if tool_round >= self.MAX_TOOL_ROUNDS:
            logger.warning(
                "Agent 工具调用达到上限",
                agent_id=self.agent.id,
                max_rounds=self.MAX_TOOL_ROUNDS,
            )

        # 解析回复：分离成果和状态报告
        final_content = messages[-1].content if messages else ""
        # 如果最后一条消息是 tool 消息，需要再调一次 LLM 获取总结
        if messages and messages[-1].role == "tool":
            try:
                summary_response = await self.model.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                )
                final_content = summary_response.content or ""
            except Exception as e:
                logger.error("Agent 总结调用失败", agent_id=self.agent.id, error=str(e))
                final_content = "工具调用完成，但总结失败。"

        status_report = self._extract_status_report(final_content)
        work_product = self._remove_status_report(final_content)

        # 将本轮对话归档回 AgentContext
        if agent_ctx:
            agent_ctx.add("thought", work_product)
            if status_report.rationale:
                agent_ctx.add("thought", status_report.rationale)
            for te in tool_events:
                for r in te.get("results", []):
                    agent_ctx.add("tool_result", r)

        logger.info(
            "Agent 执行完成",
            agent_id=self.agent.id,
            state=status_report.state,
            will=status_report.will.value,
            confidence=status_report.confidence,
            tool_rounds=tool_round,
        )

        return {
            "work_product": work_product,
            "status_report": status_report,
            "tool_events": tool_events,
        }

    async def _execute_virtual_agent(
        self,
        task: str,
        tool_executor: Optional[ToolExecutor],
        _emit,
    ) -> Dict[str, Any]:
        """虚拟工具智能体执行：跳过 LLM，直接调用工具。

        从 model_config 读取节点配置，构造 ToolCall 并执行。
        """
        node_config = self.agent.model_config.get("node_config", {})
        node_type = self.agent.model_config.get("node_type", "")

        tool_name = ""
        arguments: Dict[str, Any] = {}

        if node_type == "tool":
            tool_name = node_config.get("tool_name", "") or (self.agent.tools[0] if self.agent.tools else "")
            arguments = node_config.get("arguments", {})
        elif node_type == "mcp":
            tool_name = node_config.get("tool_name", "")
            arguments = node_config.get("arguments", {})
        else:
            # skill / artifact 暂走 LLM 路径（在 _execute_loop 中不应走到这里）
            logger.warning("虚拟智能体类型不支持直接执行", agent_id=self.agent.id, node_type=node_type)
            return {
                "work_product": f"虚拟智能体 {self.agent.name} 暂不支持直接执行",
                "status_report": AgentReport(
                    agent_id=self.agent.id,
                    state=AgentState.COMPLETED,
                    will=AgentWill.COMPLETE,
                    rationale=f"节点类型 {node_type} 不走虚拟执行路径",
                    confidence=1.0,
                ),
                "tool_events": [],
            }

        if not tool_name or not tool_executor:
            return {
                "work_product": "工具执行失败：未配置工具名或执行器",
                "status_report": AgentReport(
                    agent_id=self.agent.id,
                    state=AgentState.FAILED,
                    will=AgentWill.BLOCKED,
                    rationale="缺少工具名或工具执行器",
                    confidence=1.0,
                ),
                "tool_events": [],
            }

        logger.info("虚拟智能体直接执行工具", agent_id=self.agent.id, tool=tool_name)
        await _emit(
            "agent.tool_call",
            {
                "agent_id": self.agent.id,
                "tool_count": 1,
                "tools": [tool_name],
            },
        )

        # 构造 ToolCall 并执行
        tool_call = ToolCall(
            call_id=f"virtual_{self.agent.id}_{uuid.uuid4().hex[:8]}",
            tool_name=tool_name,
            parameters=arguments,
        )

        try:
            result = await tool_executor.execute(tool_call)
            if not isinstance(result, ToolResult):
                result = ToolResult(
                    call_id=tool_call.call_id,
                    success=True,
                    result=result,
                )
        except Exception as e:
            logger.error("虚拟智能体工具执行失败", agent_id=self.agent.id, tool=tool_name, error=str(e))
            result = ToolResult(
                call_id=tool_call.call_id,
                success=False,
                result=None,
                error=str(e),
            )

        await _emit(
            "agent.tool_result",
            {
                "agent_id": self.agent.id,
                "tool": tool_name,
                "success": result.success,
            },
        )

        tool_events = [
            {
                "agent_id": self.agent.id,
                "round": 1,
                "results": [
                    {
                        "tool": tool_name,
                        "success": result.success,
                        "result": result.result,
                    }
                ],
            }
        ]

        work_product = str(result.result) if result.success else f"工具执行失败: {result.error}"

        return {
            "work_product": work_product,
            "status_report": AgentReport(
                agent_id=self.agent.id,
                state=AgentState.COMPLETED if result.success else AgentState.FAILED,
                will=AgentWill.COMPLETE if result.success else AgentWill.BLOCKED,
                rationale=f"工具 {tool_name} 执行{'成功' if result.success else '失败'}",
                confidence=1.0,
            ),
            "tool_events": tool_events,
        }

    async def _chat_streaming(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str],
        tools: Optional[List[Dict]],
        _emit,
    ) -> ChatResponse:
        """流式对话，emit agent.token 事件，组装成 ChatResponse"""
        content_parts: List[str] = []
        # tool_calls 在流式中可能分散在多个 chunk，需要积累
        tool_calls_acc: Dict[int, Dict[str, Any]] = {}

        stream = self.model.chat_stream(
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
        )

        async for chunk in stream:
            # 1. 文本内容
            if chunk.content:
                content_parts.append(chunk.content)
                await _emit(
                    "agent.token",
                    {
                        "agent_id": self.agent.id,
                        "token": chunk.content,
                    },
                )

            # 1.5 思考过程
            if chunk.reasoning:
                await _emit(
                    "agent.thinking",
                    {
                        "agent_id": self.agent.id,
                        "thinking": chunk.reasoning,
                    },
                )

            # 2. tool_call 增量（可能跨多个 chunk）
            if chunk.tool_call:
                tc = chunk.tool_call
                idx = tc.get("index", 0)
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = tc
                else:
                    # 合并 arguments（增量追加）
                    existing = tool_calls_acc[idx]
                    if "function" in tc and "function" in existing:
                        inc_args = tc["function"].get("arguments", "")
                        existing["function"]["arguments"] = (
                            existing["function"].get("arguments", "") + inc_args
                        )

            # 3. 结束标记
            if chunk.finish_reason:
                break

        # 组装最终响应
        full_content = "".join(content_parts)
        final_tool_calls = (
            [tool_calls_acc[i] for i in sorted(tool_calls_acc.keys())] if tool_calls_acc else None
        )

        return ChatResponse(
            content=full_content,
            tool_calls=final_tool_calls,
        )

    def _build_prompt(self, task: str, blackboard_view: dict) -> str:
        """构建用户提示词"""
        # 构建 Blackboard 视图文本
        bb_text = self._format_blackboard(blackboard_view)

        return f"""你的当前任务：
{task}

全局上下文（只读）：
{bb_text}

请完成以下工作，并在最后输出你的状态报告：

---
工作状态报告（必须包含，格式如下）：
```status_report
{{
  "state": "running|ready|waiting|completed",
  "will": "execute|wait|delegate|complete|blocked",
  "rationale": "简要说明你的当前状态和下一步计划",
  "blockers": [],
  "priority": 1,
  "confidence": 0.95
}}
```
"""

    def _format_blackboard(self, blackboard_view: dict) -> str:
        """格式化 Blackboard 分层视图为文本"""
        parts = []

        # 1. 结构化摘要（替代早期历史）
        summaries = blackboard_view.get("structured_summaries", [])
        if summaries:
            parts.append("历史摘要：")
            for s in summaries[-3:]:
                content = s.get("content", "") if isinstance(s, dict) else str(s)
                parts.append(f"  - {content[:120]}")

        # 2. 近期原始记录（保留细节）
        recent_history = blackboard_view.get("recent_history", [])
        if recent_history:
            parts.append("近期历史：")
            for entry in recent_history[-5:]:
                parts.append(
                    f"  - [{entry.get('type', '?')}] {str(entry.get('content', ''))[:100]}"
                )

        # 3. 结构化键值状态
        kv_state = blackboard_view.get("kv_state", {})
        if kv_state:
            parts.append(f"状态变量：{json.dumps(kv_state, ensure_ascii=False, indent=2)}")

        version = blackboard_view.get("version", 0)
        if version:
            parts.append(f"版本：{version}")

        return "\n".join(parts) if parts else "（无）"

    def _extract_status_report(self, content: str) -> AgentReport:
        """从回复中提取状态报告"""
        import re

        pattern = r"```status_report\s*([\s\S]*?)\s*```"
        match = re.search(pattern, content)
        if match:
            try:
                data = json.loads(match.group(1))
                return AgentReport(
                    agent_id=self.agent.id,
                    state=self._parse_state(data.get("state", "unknown")),
                    will=self._parse_will(data.get("will", "wait")),
                    rationale=data.get("rationale", ""),
                    blockers=data.get("blockers", []),
                    priority=data.get("priority", 0),
                    confidence=data.get("confidence", 0.0),
                )
            except (json.JSONDecodeError, ValueError):
                pass

        return AgentReport(
            agent_id=self.agent.id,
            state=AgentState.UNKNOWN,
            will=AgentWill.WAIT,
            rationale="无法解析状态报告",
            confidence=0.0,
        )

    def _remove_status_report(self, content: str) -> str:
        """从回复中移除状态报告部分"""

        pattern = r"```status_report\s*[\s\S]*?\s*```"
        return re.sub(pattern, "", content).strip()

    def _parse_state(self, state_str: str) -> AgentState:
        """解析状态字符串"""
        state_map = {
            "idle": AgentState.IDLE,
            "ready": AgentState.READY,
            "running": AgentState.RUNNING,
            "waiting": AgentState.WAITING,
            "completed": AgentState.COMPLETED,
            "failed": AgentState.FAILED,
        }
        return state_map.get(state_str.lower(), AgentState.UNKNOWN)

    def _parse_will(self, will_str: str) -> AgentWill:
        """解析意图字符串"""
        will_map = {
            "execute": AgentWill.EXECUTE,
            "wait": AgentWill.WAIT,
            "delegate": AgentWill.DELEGATE,
            "complete": AgentWill.COMPLETE,
            "blocked": AgentWill.BLOCKED,
        }

        return will_map.get(will_str.lower(), AgentWill.WAIT)
