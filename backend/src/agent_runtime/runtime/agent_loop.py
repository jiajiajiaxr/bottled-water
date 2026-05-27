"""
Agent 执行循环

负责单个 Agent 的单轮执行：
- 构建上下文（私有栈 + Blackboard 视图）
- 调用 LLM（支持工具调用）
- 处理工具调用（多轮）
- 状态自报告
"""

import json
from typing import Dict, Any, Optional, List

from model_provider.core.interfaces import BaseModelProvider, ChatMessage

from common.logger import get_logger
from ..core.types import AgentConfig, AgentReport, AgentState, AgentWill, ToolCall, ToolResult
from ..core.interfaces import ToolExecutor

logger = get_logger(__name__)


class AgentLoop:
    """Agent 执行循环"""

    MAX_TOOL_ROUNDS = 10  # 最大工具调用轮数，防止无限循环

    def __init__(
        self,
        agent_config: AgentConfig,
        model_provider: BaseModelProvider,
    ):
        self.agent = agent_config
        self.model = model_provider

    async def run(
        self,
        task: str,
        blackboard_view: dict,
        tool_executor: Optional[ToolExecutor] = None,
    ) -> Dict[str, Any]:
        """
        执行 Agent 单轮任务。

        流程：
        1. 构建系统提示词和用户提示词
        2. 调用 LLM（带工具列表）
        3. 如果 LLM 返回 tool_calls，执行工具并回传结果
        4. 重复步骤 2-3 直到 LLM 不再调用工具或达到上限
        5. 解析最终回复，提取成果和状态报告

        Returns:
            {"work_product": str, "status_report": AgentReport}
        """
        logger.info("Agent 执行开始", agent_id=self.agent.id, task=task[:50])

        # 构建系统提示词
        system_prompt = self.agent.system_prompt

        # 构建消息列表
        messages: List[ChatMessage] = []

        # 构建用户提示词
        user_prompt = self._build_prompt(task, blackboard_view)
        messages.append(ChatMessage(role="user", content=user_prompt))

        # 获取可用工具
        tools = []
        if tool_executor:
            tools = tool_executor.list_tools()
            logger.debug("Agent 可用工具", agent_id=self.agent.id, tool_count=len(tools))

        # 工具调用循环
        tool_results: List[Dict[str, Any]] = []
        tool_events: List[Dict[str, Any]] = []
        tool_round = 0

        while tool_round < self.MAX_TOOL_ROUNDS:
            tool_round += 1

            try:
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
                break

            # 处理工具调用
            logger.info(
                "Agent 工具调用",
                agent_id=self.agent.id,
                tool_count=len(tool_calls),
                round=tool_round,
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

                result = await self._execute_tool_call(tc, tool_executor)
                tool_results.append({
                    "tool": tc.get("function", {}).get("name", "unknown"),
                    "success": result.success if isinstance(result, ToolResult) else True,
                    "result": result.result if isinstance(result, ToolResult) else result,
                })

                # 将工具结果加入消息列表
                tool_msg = ChatMessage(
                    role="tool",
                    content=str(result.result if isinstance(result, ToolResult) else result),
                    name=tc.get("function", {}).get("name", "unknown"),
                )
                messages.append(tool_msg)

            tool_events.append({
                "agent_id": self.agent.id,
                "round": tool_round,
                "results": tool_results[-len(tool_calls):],
            })

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

    async def _execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        tool_executor: ToolExecutor,
    ) -> ToolResult:
        """执行单个工具调用"""
        function_info = tool_call.get("function", {})
        tool_name = function_info.get("name", "")
        arguments_str = function_info.get("arguments", "{}")
        call_id = tool_call.get("id", "")

        logger.info("执行工具", agent_id=self.agent.id, tool=tool_name, call_id=call_id)

        try:
            # 解析参数
            if isinstance(arguments_str, str):
                parameters = json.loads(arguments_str)
            else:
                parameters = arguments_str

            # 执行工具
            result = await tool_executor.execute(tool_name, parameters)

            # 如果 result 已经是 ToolResult，直接返回
            if isinstance(result, ToolResult):
                return result

            # 否则包装为 ToolResult
            return ToolResult(
                call_id=call_id,
                success=True,
                result=result,
            )
        except json.JSONDecodeError as e:
            logger.error("工具参数解析失败", tool=tool_name, error=str(e))
            return ToolResult(
                call_id=call_id,
                success=False,
                result=None,
                error=f"参数解析失败: {e}",
            )
        except Exception as e:
            logger.error("工具执行失败", tool=tool_name, error=str(e))
            return ToolResult(
                call_id=call_id,
                success=False,
                result=None,
                error=str(e),
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
        """格式化 Blackboard 视图为文本"""
        parts = []

        recent_history = blackboard_view.get("recent_history", [])
        if recent_history:
            parts.append("近期历史：")
            for entry in recent_history[-5:]:
                parts.append(f"  - [{entry.get('type', '?')}] {str(entry.get('content', ''))[:100]}")

        kv_state = blackboard_view.get("kv_state", {})
        if kv_state:
            parts.append(f"状态变量：{json.dumps(kv_state, ensure_ascii=False, indent=2)}")

        summary_count = blackboard_view.get("summary_count", 0)
        if summary_count:
            parts.append(f"结构化摘要数：{summary_count}")

        version = blackboard_view.get("version", 0)
        parts.append(f"版本：{version}")

        return "\n".join(parts) if parts else "（无）"

    def _extract_status_report(self, content: str) -> AgentReport:
        """从回复中提取状态报告"""
        import re

        pattern = r'```status_report\s*([\s\S]*?)\s*```'
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
        import re
        pattern = r'```status_report\s*[\s\S]*?\s*```'
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
