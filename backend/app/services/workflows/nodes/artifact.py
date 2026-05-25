from __future__ import annotations

from app.services.artifacts import build_demo_html, create_artifact, create_preview_message
from app.services.serialization import artifact_to_dict, message_to_dict
from app.services.realtime.event_bus import event_bus
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor, resolve_references


class ArtifactNodeExecutor(WorkflowNodeExecutor):
    node_type = "artifact"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        artifact_type = str(node.config.get("artifact_type") or "html")
        name = str(resolve_references(node.config.get("name") or f"{node.title} Artifact", context.outputs))
        artifact = create_artifact(
            context.db,
            context.conversation,
            task=context.task,
            name=name,
            html=build_demo_html(context.prompt, "Workflow artifact generated.", artifact_type=artifact_type),
            artifact_type=artifact_type,
        )
        preview = create_preview_message(context.db, context.conversation, artifact)
        context.db.commit()
        await event_bus.publish(context.channel, "artifact:created", artifact_to_dict(artifact))
        await event_bus.publish(context.channel, "message:new", message_to_dict(preview))
        return NodeExecutionResult(output={"artifact_id": artifact.id, "preview_message_id": preview.id})
