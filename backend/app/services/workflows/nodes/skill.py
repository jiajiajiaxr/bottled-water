from __future__ import annotations

from app.models import Skill, User
from app.services.agents.tool_loop import execute_skill
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor, resolve_references


class SkillNodeExecutor(WorkflowNodeExecutor):
    node_type = "skill"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        skill_id = str(node.config.get("skill_id") or "")
        skill = context.db.get(Skill, skill_id) if skill_id else None
        if not skill or skill.deleted_at is not None:
            return NodeExecutionResult(status="skipped", output={"reason": "skill not found"})
        user = context.db.get(User, context.conversation.creator_id)
        result = await execute_skill(
            context.db,
            skill=skill,
            user=user,
            conversation=context.conversation,
            prompt=str(resolve_references(node.config.get("prompt") or context.prompt, context.outputs)),
        )
        return NodeExecutionResult(output={"skill_id": skill_id, "result": result}, message=f"Skill {skill.name} completed")
