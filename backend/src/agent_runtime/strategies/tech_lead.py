"""
技术负责人调度策略

模拟技术团队 Leader 的调度风格。
基于 LLM 推理做调度决策，但受看门狗约束。
"""

import json
from typing import Dict, List, Any, Optional

from model_provider.core.interfaces import BaseModelProvider, ChatMessage
from model_provider.core.config import ModelConfig
from model_provider.factory import create_provider

from common.logger import get_logger
from .base import Scheduler
from ..core.types import AgentReport, SchedulingDecision, AgentConfig

logger = get_logger(__name__)


class TechLeadScheduler(Scheduler):
    """技术负责人调度员

    使用 LLM 做语义调度决策，具备以下特点：
    - 理解 Agent 的能力和当前状态
    - 根据任务类型分派给合适的 Agent
    - 识别依赖关系，避免死锁
    - 在需要时请求用户输入或升级
    """

    SYSTEM_PROMPT = """你是技术团队的负责人，负责协调团队成员完成技术任务。

你的职责：
1. 分析全局上下文和团队成员状态
2. 决定下一步如何调度（指派、并行、等待、升级、请求用户输入）
3. 确保任务高效完成，避免死锁和无效循环

可用的决策类型：
- assign: 指派某个 Agent 执行具体任务
- parallel: 多个 Agent 并行执行（用于独立子任务）
- wait: 等待（当前条件不满足，需要等待外部事件）
- escalate: 升级（任务超出团队能力，需要人工介入）
- user_input: 请求用户输入（需要更多信息才能继续）
- complete: 任务已完成，结束会话

团队成员信息：
{agent_profiles}

当前全局上下文：
{blackboard_summary}

各成员状态报告：
{agent_reports}

请输出调度决策 JSON（不要有其他输出）：
{{
  "decision_type": "assign|parallel|wait|escalate|user_input|complete",
  "target_agent_id": "xxx",
  "task_description": "...",
  "rationale": "...",
  "requires_verification": true|false,
  "verification_agents": ["reviewer_id"]
}}
"""

    def __init__(
        self,
        agents: Dict[str, AgentConfig] = None,
        model_provider: Optional[BaseModelProvider] = None,
        model_config: Optional[ModelConfig] = None,
    ):
        """
        Args:
            agents: Agent 配置字典
            model_provider: 直接使用模型提供者实例（推荐）
            model_config: 模型配置，用于创建模型提供者（备选）
        """
        super().__init__(agents or {})
        self.model_provider = model_provider
        if model_provider is None and model_config is not None:
            self.model_provider = create_provider(model_config)

    async def make_decision(
        self,
        blackboard: Dict[str, Any],
        agent_reports: List[AgentReport],
        conversation_context: Dict[str, Any]
    ) -> SchedulingDecision:
        """基于 LLM 推理做调度决策"""
        if self.model_provider is None:
            logger.warning("TechLeadScheduler 未配置模型，使用回退策略")
            return self._fallback_decision(agent_reports)

        try:
            return await self._llm_decision(blackboard, agent_reports, conversation_context)
        except Exception as e:
            logger.error("LLM 调度决策失败", error=str(e))
            return self._fallback_decision(agent_reports)

    async def _llm_decision(
        self,
        blackboard: Dict[str, Any],
        agent_reports: List[AgentReport],
        conversation_context: Dict[str, Any]
    ) -> SchedulingDecision:
        """调用 LLM 做调度决策"""
        # 构建 prompt
        agent_profiles = self._build_agent_profiles()
        blackboard_summary = self._build_blackboard_summary(blackboard)
        reports_text = self._build_reports_text(agent_reports)

        system_prompt = self.SYSTEM_PROMPT.format(
            agent_profiles=agent_profiles,
            blackboard_summary=blackboard_summary,
            agent_reports=reports_text,
        )

        user_prompt = f"""当前回合：{conversation_context.get("round", 0)}
会话ID：{conversation_context.get("session_id", "unknown")}
当前任务：{conversation_context.get("current_task", "无")}
Agent 数量：{conversation_context.get("agent_count", 0)}

请基于以上信息做出调度决策。"""

        logger.info("LLM 调度决策请求", round=conversation_context.get("round"))

        # 调用 LLM
        response = await self.model_provider.chat(
            messages=[ChatMessage(role="user", content=user_prompt)],
            system_prompt=system_prompt,
            temperature=0.3,  # 调度决策需要确定性
        )

        # 解析 JSON
        decision_data = self._parse_decision_json(response.content)
        logger.info(
            "LLM 调度决策完成",
            decision=decision_data.get("decision_type"),
            target=decision_data.get("target_agent_id"),
        )

        return SchedulingDecision(
            decision_type=decision_data.get("decision_type", "wait"),
            target_agent_id=decision_data.get("target_agent_id"),
            task_description=decision_data.get("task_description", ""),
            rationale=decision_data.get("rationale", ""),
            requires_verification=decision_data.get("requires_verification", False),
            verification_agents=decision_data.get("verification_agents", []),
        )

    def _parse_decision_json(self, content: str) -> Dict[str, Any]:
        """从 LLM 响应中解析 JSON"""
        # 先尝试直接解析
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        import re
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{[\s\S]*\}',
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    continue

        # 回退：尝试找到第一个 JSON 对象
        try:
            start = content.index('{')
            end = content.rindex('}') + 1
            return json.loads(content[start:end])
        except (ValueError, json.JSONDecodeError):
            pass

        logger.warning("无法解析调度决策 JSON", content=content[:200])
        return {"decision_type": "wait", "rationale": "无法解析 LLM 响应"}

    def _fallback_decision(self, agent_reports: List[AgentReport]) -> SchedulingDecision:
        """回退策略：选择第一个 ready 的 agent"""
        for report in agent_reports:
            if report.state == "ready":
                return SchedulingDecision(
                    decision_type="assign",
                    target_agent_id=report.agent_id,
                    task_description="执行当前任务",
                    rationale="Agent 已就绪（回退策略）",
                )

        # 如果所有 agent 都已完成
        all_completed = all(r.state == "completed" for r in agent_reports)
        if all_completed:
            return SchedulingDecision(
                decision_type="complete",
                rationale="所有 Agent 已完成",
            )

        return SchedulingDecision(
            decision_type="wait",
            rationale="没有就绪的 Agent（回退策略）",
        )

    def _build_agent_profiles(self) -> str:
        """构建 Agent 配置描述"""
        lines = []
        for agent_id, agent in self.agents.items():
            lines.append(f"- {agent.name} (ID: {agent_id}, 角色: {agent.role})")
            lines.append(f"  系统提示：{agent.system_prompt[:100]}...")
            if agent.tools:
                lines.append(f"  可用工具：{', '.join(agent.tools)}")
        return "\n".join(lines)

    def _build_blackboard_summary(self, blackboard: Dict[str, Any]) -> str:
        """构建 Blackboard 摘要"""
        parts = []
        history = blackboard.get("recent_history", blackboard.get("raw_history", []))
        if history:
            parts.append(f"历史记录数：{len(history)}")
            recent = history[-3:] if len(history) > 3 else history
            for entry in recent:
                parts.append(f"  - [{entry.get('type', '?')}] {str(entry.get('content', ''))[:80]}...")

        kv = blackboard.get("kv_state", {})
        if kv:
            parts.append(f"键值状态：{list(kv.keys())}")

        summaries = blackboard.get("structured_summaries", [])
        if summaries:
            parts.append(f"结构化摘要数：{len(summaries)}")

        version = blackboard.get("version", 0)
        parts.append(f"版本：{version}")

        return "\n".join(parts) if parts else "Blackboard 为空"

    def _build_reports_text(self, reports: List[AgentReport]) -> str:
        """构建 Agent 报告文本"""
        lines = []
        for r in reports:
            lines.append(f"- {r.agent_id}: state={r.state}, will={r.will.value}")
            if r.rationale:
                lines.append(f"  理由：{r.rationale}")
            if r.blockers:
                lines.append(f"  阻塞：{r.blockers}")
            if r.confidence:
                lines.append(f"  置信度：{r.confidence}")
        return "\n".join(lines)

    async def resolve_conflict(
        self,
        conflict_type: str,
        conflicting_reports: List[AgentReport],
        blackboard: Dict[str, Any]
    ) -> SchedulingDecision:
        """解决 Agent 之间的冲突"""
        if self.model_provider is None:
            return SchedulingDecision(
                decision_type="assign",
                target_agent_id=conflicting_reports[0].agent_id,
                rationale="冲突解决：选择第一个（回退策略）",
            )

        try:
            prompt = f"""冲突类型：{conflict_type}

冲突的 Agent：
{self._build_reports_text(conflicting_reports)}

全局上下文：
{self._build_blackboard_summary(blackboard)}

请决定如何解决这个冲突，输出 JSON：
{{
  "target_agent_id": "xxx",
  "rationale": "..."
}}"""

            response = await self.model_provider.chat(
                messages=[ChatMessage(role="user", content=prompt)],
                system_prompt="你是冲突调解专家。请分析冲突并给出公正的解决方案。",
                temperature=0.3,
            )

            data = self._parse_decision_json(response.content)
            return SchedulingDecision(
                decision_type="assign",
                target_agent_id=data.get("target_agent_id", conflicting_reports[0].agent_id),
                rationale=data.get("rationale", "LLM 冲突解决"),
            )
        except Exception as e:
            logger.error("LLM 冲突解决失败", error=str(e))
            return SchedulingDecision(
                decision_type="assign",
                target_agent_id=conflicting_reports[0].agent_id,
                rationale="冲突解决失败，选择第一个（回退策略）",
            )
