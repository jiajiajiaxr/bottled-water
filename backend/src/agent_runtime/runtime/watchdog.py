"""
看门狗 - 调度循环的安全守卫

负责：
- 轮数上限控制
- 死锁/停滞检测
- Token 预算控制
- 决策合规性校验

看门狗是"最后一道防线"，不干预正常调度，只在异常时触发。
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from common.logger import get_logger
from ..core.types import AgentReport, SchedulingDecision, Event

logger = get_logger(__name__)


@dataclass
class WatchdogConfig:
    """看门狗配置"""
    max_rounds: int = 50           # 最大调度轮数
    max_idle_seconds: int = 300    # 最大空闲时间（秒）
    max_total_tokens: int = 500000  # Token 预算上限
    deadlock_threshold: int = 3    # 死锁检测：连续 N 轮无进展
    min_progress_interval: int = 10  # 最小进展间隔（秒）


@dataclass
class WatchdogState:
    """看门狗内部状态"""
    round_count: int = 0
    total_tokens_used: int = 0
    last_progress_round: int = 0
    last_progress_time: Optional[datetime] = None
    idle_agent_count: int = 0
    consecutive_idle_rounds: int = 0
    decision_history: List[Dict] = field(default_factory=list)


class Watchdog:
    """看门狗"""

    def __init__(self, config: Optional[WatchdogConfig] = None):
        self.config = config or WatchdogConfig()
        self.state = WatchdogState()
        self.started_at = datetime.utcnow()

    # --- 决策前校验 ---

    def check_before_decision(self, blackboard: dict, reports: List[AgentReport]) -> Optional[Event]:
        """
        调度器决策前校验。

        Returns:
            如果校验通过返回 None，否则返回终止事件。
        """
        self.state.round_count += 1

        # 1. 轮数上限
        if self.state.round_count > self.config.max_rounds:
            logger.warning("看门狗触发：轮数上限", rounds=self.state.round_count, max_rounds=self.config.max_rounds)
            return Event(
                type="watchdog_triggered",
                payload={
                    "reason": "max_rounds_exceeded",
                    "rounds": self.state.round_count,
                    "max_rounds": self.config.max_rounds,
                },
            )

        # 2. Token 预算
        if self.state.total_tokens_used > self.config.max_total_tokens:
            logger.warning(
                "看门狗触发：Token 预算耗尽",
                tokens=self.state.total_tokens_used,
                max_tokens=self.config.max_total_tokens,
            )
            return Event(
                type="watchdog_triggered",
                payload={
                    "reason": "token_budget_exhausted",
                    "tokens_used": self.state.total_tokens_used,
                    "max_tokens": self.config.max_total_tokens,
                },
            )

        # 3. 死锁/停滞检测
        active_count = sum(1 for r in reports if r.state not in ("completed", "failed"))
        all_blocked = all(r.will.value == "blocked" for r in reports)
        all_waiting = all(r.will.value == "wait" for r in reports)

        if active_count == 0 or all_blocked or all_waiting:
            self.state.consecutive_idle_rounds += 1
            if self.state.consecutive_idle_rounds >= self.config.deadlock_threshold:
                logger.warning(
                    "看门狗触发：死锁/停滞",
                    consecutive_idle=self.state.consecutive_idle_rounds,
                )
                return Event(
                    type="watchdog_triggered",
                    payload={
                        "reason": "deadlock_detected",
                        "consecutive_idle_rounds": self.state.consecutive_idle_rounds,
                        "agent_states": [r.state for r in reports],
                    },
                )
        else:
            self.state.consecutive_idle_rounds = 0

        # 4. 运行超时
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        if elapsed > self.config.max_idle_seconds:
            logger.warning("看门狗触发：运行超时", elapsed=elapsed, max_seconds=self.config.max_idle_seconds)
            return Event(
                type="watchdog_triggered",
                payload={
                    "reason": "timeout",
                    "elapsed_seconds": elapsed,
                    "max_seconds": self.config.max_idle_seconds,
                },
            )

        return None

    # --- 决策后校验 ---

    def check_after_decision(self, decision: SchedulingDecision) -> Optional[Event]:
        """
        调度器决策后校验。

        Returns:
            如果校验通过返回 None，否则返回终止事件。
        """
        self.state.decision_history.append({
            "round": self.state.round_count,
            "decision_type": decision.decision_type,
            "target": decision.target_agent_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # 检测连续重复的决策（可能陷入循环）
        if len(self.state.decision_history) >= 4:
            recent = self.state.decision_history[-4:]
            if all(d["decision_type"] == recent[0]["decision_type"] and d["target"] == recent[0]["target"] for d in recent):
                logger.warning(
                    "看门狗触发：决策循环",
                    target=decision.target_agent_id,
                    decision_type=decision.decision_type,
                )
                return Event(
                    type="watchdog_triggered",
                    payload={
                        "reason": "decision_loop",
                        "repeated_target": decision.target_agent_id,
                        "repeated_decision_type": decision.decision_type,
                    },
                )

        return None

    # --- 进展跟踪 ---

    def record_progress(self, tokens_used: int = 0):
        """记录一轮进展"""
        self.state.last_progress_round = self.state.round_count
        self.state.last_progress_time = datetime.utcnow()
        self.state.total_tokens_used += tokens_used
        self.state.consecutive_idle_rounds = 0

    def record_no_progress(self):
        """记录一轮无进展"""
        pass  # 由 check_before_decision 处理连续计数

    # --- Token 跟踪 ---

    def add_tokens(self, tokens: int):
        """增加 Token 使用量"""
        self.state.total_tokens_used += tokens

    # --- 状态查询 ---

    def get_status(self) -> dict:
        """获取看门狗状态"""
        return {
            "round_count": self.state.round_count,
            "total_tokens_used": self.state.total_tokens_used,
            "consecutive_idle_rounds": self.state.consecutive_idle_rounds,
            "started_at": self.started_at.isoformat(),
            "config": {
                "max_rounds": self.config.max_rounds,
                "max_idle_seconds": self.config.max_idle_seconds,
                "max_total_tokens": self.config.max_total_tokens,
                "deadlock_threshold": self.config.deadlock_threshold,
            },
        }
