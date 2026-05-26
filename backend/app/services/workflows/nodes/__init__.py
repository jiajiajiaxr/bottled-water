from __future__ import annotations

from app.services.workflows.nodes.agent import AgentNodeExecutor, ReviewNodeExecutor
from app.services.workflows.nodes.artifact import ArtifactNodeExecutor
from app.services.workflows.nodes.base import WorkflowNodeExecutor
from app.services.workflows.nodes.condition import ConditionNodeExecutor
from app.services.workflows.nodes.end import EndNodeExecutor
from app.services.workflows.nodes.loop import LoopNodeExecutor
from app.services.workflows.nodes.mcp import McpNodeExecutor
from app.services.workflows.nodes.skill import SkillNodeExecutor
from app.services.workflows.nodes.start import StartNodeExecutor
from app.services.workflows.nodes.tool import ToolNodeExecutor


EXECUTORS: dict[str, WorkflowNodeExecutor] = {
    "start": StartNodeExecutor(),
    "agent": AgentNodeExecutor(),
    "review": ReviewNodeExecutor(),
    "tool": ToolNodeExecutor(),
    "skill": SkillNodeExecutor(),
    "mcp": McpNodeExecutor(),
    "condition": ConditionNodeExecutor(),
    "loop": LoopNodeExecutor(),
    "artifact": ArtifactNodeExecutor(),
    "end": EndNodeExecutor(),
}


def get_executor(node_type: str) -> WorkflowNodeExecutor:
    return EXECUTORS.get(node_type, WorkflowNodeExecutor())
