from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, utcnow
from app.services.ark import ark_client
from app.services.llm_gateway import stream_model_config
from app.services.output_filter import strip_internal_agent_output
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict


async def _run_canvas_agent_reply(
    db: Session,
    *,
    conversation: Conversation,
    agent: Agent,
    prompt: str,
    channel: str,
    tool_context: dict[str, Any],
) -> str:
    assistant = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=agent.id,
        sender_name=agent.name,
        content_type="text",
        content={"text": ""},
        status="streaming",
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)
    await event_bus.publish(channel, "message_start", {"agent_message_id": assistant.id, "agent_id": agent.id, "agent_name": agent.name})

    stream_text = ""
    system_prompt = (agent.config or {}).get("system_prompt") or agent.description or f"You are {agent.name}."
    system_prompt += (
        "\nYou are replying as yourself in an AgentHub group chat. "
        "Do not pretend to be Master Agent unless your own name/type is Master. "
        "Use only your authorized tools, skills, MCP results, and role expertise. "
        "Return a concise, user-facing answer without internal planning sections."
    )
    tool_summary = json.dumps(tool_context, ensure_ascii=False)[:6000]
    model_config_id = (agent.config or {}).get("model_config_id")
    if model_config_id:
        try:
            async for chunk in stream_model_config(
                db,
                str(model_config_id),
                f"{system_prompt}\n\nTool context:\n{tool_summary}\n\nUser:\n{prompt}",
            ):
                text = chunk.get("text", "")
                if text:
                    stream_text += text
                    await event_bus.publish(
                        channel,
                        "content_block_delta",
                        {"agent_message_id": assistant.id, "delta": {"type": "text_delta", "text": text}},
                    )
        except Exception as exc:
            stream_text = f"{agent.name} model call failed and fell back: {exc}"
            await event_bus.publish(
                channel,
                "content_block_delta",
                {"agent_message_id": assistant.id, "delta": {"type": "text_delta", "text": stream_text}},
            )
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"Tool context:\n{tool_summary}"},
            {"role": "user", "content": prompt},
        ]
        async for event in ark_client.stream_chat(messages, purpose=f"group_agent:{agent.type}"):
            if event.type == "delta":
                stream_text += event.text
                await event_bus.publish(
                    channel,
                    "content_block_delta",
                    {"agent_message_id": assistant.id, "delta": {"type": "text_delta", "text": event.text}},
                )
            elif event.type == "error":
                stream_text += f"\nModel call failed and fell back: {event.error}"

    display_text = strip_internal_agent_output(stream_text)
    assistant.content = {"text": display_text or f"{agent.name} completed this turn."}
    assistant.status = "completed"
    conversation.last_message_preview = assistant.content["text"][:300]
    conversation.last_message_sender = agent.name
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 4)
    conversation.message_count += 1
    db.commit()
    await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
    return assistant.content["text"]
