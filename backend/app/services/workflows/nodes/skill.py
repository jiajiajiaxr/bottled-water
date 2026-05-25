from __future__ import annotations

from app.models import Skill, User
from app.services.agents.tool_loop import execute_skill
from app.services.workflows.events import publish_tool_event
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor, resolve_references


class SkillNodeExecutor(WorkflowNodeExecutor):
    node_type = "skill"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        skill_id = str(node.config.get("skill_id") or "")
        skill = context.db.get(Skill, skill_id) if skill_id else None
        if not skill or skill.deleted_at is not None:
            return NodeExecutionResult(status="failed", output={"error": "skill not found", "skill_id": skill_id})
        user = context.db.get(User, context.conversation.creator_id)
        prompt = str(resolve_references(node.config.get("prompt") or context.prompt, context.outputs))
        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_started",
            {"type": "skill", "skill_id": skill_id},
        )
        result = await execute_skill(
            context.db,
            skill=skill,
            user=user,
            conversation=context.conversation,
            prompt=prompt,
        )
        status = str(result.get("status") or "succeeded")
        node_status = "failed" if status.startswith("failed") or status == "error" else "completed"
        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_completed",
            {"type": "skill", "skill_id": skill_id, "status": status},
        )
        return NodeExecutionResult(
            status=node_status,
            output={
                "skill_id": skill_id,
                "prompt": prompt,
                "result": result,
                **({"error": str(result.get("output") or result)} if node_status == "failed" else {}),
            },
            message=f"Skill {skill.name} {status}",
        )
