from __future__ import annotations

from app.services.artifacts import build_demo_html, create_artifact, create_preview_message
from app.services.serialization import artifact_to_dict, message_to_dict
from app.services.realtime.event_bus import event_bus
from app.services.workflows.graph import Node
from app.services.workflows.io import resolve_value
from app.services.workflows.nodes.base import (
    NodeExecutionResult,
    WorkflowExecutionContext,
    WorkflowNodeExecutor,
)


class ArtifactNodeExecutor(WorkflowNodeExecutor):
    node_type = "artifact"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        artifact_type = str(node.config.get("artifact_type") or "html")
        node_input = getattr(context, "node_input", {}) or {}
        scope = {
            "input": context.prompt,
            "nodes": context.outputs,
            "upstream": {
                "nodes": node_input.get("upstream", {}),
                "text": node_input.get("upstream_text", ""),
            },
        }
        name = str(resolve_value(node.config.get("name") or f"{node.title} Artifact", scope))
        artifact_prompt = str(
            node_input.get("content")
            or node_input.get("text")
            or node_input.get("upstream_text")
            or context.prompt
        )
        artifact = create_artifact(
            context.db,
            context.conversation,
            task=context.task,
            name=name,
            html=build_demo_html(
                artifact_prompt,
                "Workflow artifact generated.",
                artifact_type=artifact_type,
            ),
            artifact_type=artifact_type,
        )
        preview = create_preview_message(context.db, context.conversation, artifact)
        context.db.commit()
        await event_bus.publish(context.channel, "artifact:created", artifact_to_dict(artifact))
        await event_bus.publish(context.channel, "message:new", message_to_dict(preview))
        return NodeExecutionResult(
            output={"artifact_id": artifact.id, "preview_message_id": preview.id}
        )
