from __future__ import annotations

from typing import Any

from app.models import Agent, Artifact, Message, User
from app.services.agents.tool_loop import execute_tool_by_name
from app.services.serialization import artifact_to_dict, message_to_dict
from app.services.realtime.event_bus import event_bus
from app.services.workflows.events import publish_tool_event
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
        tool_name = _artifact_tool_name(node)
        arguments = _artifact_arguments(
            node,
            scope=scope,
            title=name,
            body=artifact_prompt,
            conversation_id=str(context.conversation.id),
        )
        agent = _artifact_tool_agent(node, tool_name)
        user = context.db.get(User, context.conversation.creator_id)

        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_started",
            {"tool_name": tool_name, "arguments": arguments},
        )
        payload = await execute_tool_by_name(
            context.db,
            agent=agent,
            user=user,
            conversation=context.conversation,
            tool_name=tool_name,
            arguments=arguments,
        )
        output = _artifact_output(payload)
        status = str(payload.get("status") or output.get("status") or "succeeded")
        node_status = "failed" if status.startswith("failed") or status == "error" else "completed"
        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_completed",
            {"tool_name": tool_name, "status": status, "artifact_id": output.get("artifact_id")},
        )
        if node_status == "completed":
            await _publish_artifact_messages(context, output)
        return NodeExecutionResult(
            status=node_status,
            output={
                "tool_name": tool_name,
                "artifact_id": output.get("artifact_id"),
                "preview_message_id": output.get("preview_message_id"),
                "preview_url": output.get("preview_url"),
                "export_url": output.get("export_url"),
                "format": output.get("format"),
                "filename": output.get("filename"),
                "media_type": output.get("media_type"),
                "tool_result": payload,
                **({"error": str(output.get("error") or payload)} if node_status == "failed" else {}),
            },
            message=f"Artifact {tool_name} {status}",
        )


def _artifact_tool_name(node: Node) -> str:
    explicit = node.config.get("tool_name")
    if explicit:
        return str(explicit)
    raw = str(
        node.config.get("artifact_type")
        or node.config.get("format")
        or node.config.get("output_format")
        or "html"
    ).lower().strip(".")
    aliases = {
        "pdf": "artifact.create_pdf",
        "doc": "artifact.create_docx",
        "docx": "artifact.create_docx",
        "word": "artifact.create_docx",
        "xlsx": "artifact.create_xlsx",
        "excel": "artifact.create_xlsx",
        "ppt": "artifact.create_pptx",
        "pptx": "artifact.create_pptx",
        "slides": "artifact.create_pptx",
        "html": "artifact.create_html",
        "web": "artifact.create_web_app",
        "web_app": "artifact.create_web_app",
        "document": "artifact.create_pdf",
        "spreadsheet": "artifact.create_xlsx",
    }
    return aliases.get(raw, "artifact.create_html")


def _artifact_arguments(
    node: Node,
    *,
    scope: dict[str, Any],
    title: str,
    body: str,
    conversation_id: str,
) -> dict[str, Any]:
    arguments = {
        "conversation_id": conversation_id,
        "title": title,
        "body": body,
        "prompt": body,
        "input": body,
    }
    for key in ("html", "template", "content_model"):
        value = node.config.get(key)
        if value is not None:
            arguments[key] = resolve_value(value, scope)
    legacy_arguments = node.config.get("arguments")
    if isinstance(legacy_arguments, dict):
        arguments.update(resolve_value(legacy_arguments, scope))
    return arguments


def _artifact_tool_agent(node: Node, tool_name: str) -> Agent:
    return Agent(
        id=f"workflow-artifact-{node.id}",
        name=node.title or "Workflow Artifact Node",
        type="artifact",
        config={"tools": [tool_name]},
    )


def _artifact_output(payload: dict[str, Any]) -> dict[str, Any]:
    output = payload.get("output")
    if isinstance(output, dict):
        return output
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    return payload


async def _publish_artifact_messages(context: WorkflowExecutionContext, output: dict[str, Any]) -> None:
    artifact_payload = output.get("artifact")
    if isinstance(artifact_payload, dict):
        await event_bus.publish(context.channel, "artifact:created", artifact_payload)
    else:
        artifact_id = output.get("artifact_id")
        artifact = context.db.get(Artifact, str(artifact_id)) if artifact_id else None
        if artifact:
            await event_bus.publish(context.channel, "artifact:created", artifact_to_dict(artifact))

    preview_id = output.get("preview_message_id")
    preview = context.db.get(Message, str(preview_id)) if preview_id else None
    if preview:
        await event_bus.publish(context.channel, "message:new", message_to_dict(preview))
