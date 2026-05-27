"""
Agent 私有上下文管理器

每个 Agent 有自己的"栈"，支持压栈/弹栈/归档/清理。
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ContextFrame:
    """上下文栈帧"""
    frame_type: str  # "task" | "thought" | "tool_call" | "tool_result"
    content: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)


class AgentContext:
    """Agent 私有上下文（栈结构）"""

    def __init__(self, agent_id: str, conversation_id: str):
        self.agent_id = agent_id
        self.conversation_id = conversation_id
        self.system_prompt: str = ""
        self.role_config: Dict[str, Any] = {}
        self.stack: List[ContextFrame] = []
        self.current_round: int = 0
        self.current_task: str = ""

    def push(self, frame_type: str, content: Any):
        """压栈"""
        self.stack.append(ContextFrame(frame_type=frame_type, content=content))

    def pop(self) -> Optional[ContextFrame]:
        """弹栈"""
        if self.stack:
            return self.stack.pop()
        return None

    def peek(self, frame_type: str = None) -> Optional[ContextFrame]:
        """查看栈顶"""
        if not self.stack:
            return None
        if frame_type:
            for frame in reversed(self.stack):
                if frame.frame_type == frame_type:
                    return frame
            return None
        return self.stack[-1]

    def get_full_context(self) -> str:
        """获取完整上下文文本（用于 LLM 调用）"""
        parts = [f"系统提示：{self.system_prompt}\n"]
        for frame in self.stack:
            if frame.frame_type == "task":
                parts.append(f"当前任务：{frame.content}\n")
            elif frame.frame_type == "thought":
                parts.append(f"思考：{frame.content}\n")
            elif frame.frame_type == "tool_call":
                parts.append(f"工具调用：{frame.content}\n")
            elif frame.frame_type == "tool_result":
                parts.append(f"工具返回：{frame.content}\n")
        return "\n".join(parts)

    def archive(self) -> Dict[str, Any]:
        """归档当前上下文"""
        return {
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "stack": [
                {"type": f.frame_type, "content": f.content, "timestamp": f.timestamp.isoformat()}
                for f in self.stack
            ],
            "archived_at": datetime.utcnow().isoformat(),
        }

    def clear(self):
        """清理动态内容（节省 Token）"""
        self.stack = []


class AgentContextManager:
    """Agent Context 管理器"""

    def __init__(self):
        self._contexts: Dict[str, AgentContext] = {}

    def _key(self, agent_id: str, conversation_id: str) -> str:
        return f"{agent_id}:{conversation_id}"

    def initialize(self, agent_id: str, conversation_id: str, system_prompt: str = "", role_config: Dict = None):
        """初始化 Agent 上下文"""
        key = self._key(agent_id, conversation_id)
        ctx = AgentContext(agent_id=agent_id, conversation_id=conversation_id)
        ctx.system_prompt = system_prompt
        ctx.role_config = role_config or {}
        self._contexts[key] = ctx

    def get(self, agent_id: str, conversation_id: str) -> AgentContext:
        """获取 Agent 上下文"""
        key = self._key(agent_id, conversation_id)
        if key not in self._contexts:
            self.initialize(agent_id, conversation_id)
        return self._contexts[key]

    def after_round(self, agent_id: str, conversation_id: str, archive: bool = False) -> Optional[Dict]:
        """轮次结束后处理"""
        ctx = self.get(agent_id, conversation_id)
        result = None
        if archive:
            result = ctx.archive()
        ctx.clear()
        return result
