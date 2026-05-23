from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.events import event_bus


router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    subscribed: set[str] = set()
    try:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "data": {"message": "JSON 格式错误"}})
                continue
            event = payload.get("event")
            data = payload.get("data") or {}
            if event == "ping":
                await websocket.send_json({"event": "pong", "data": {}})
            elif event == "subscribe":
                channel = data.get("channel")
                if channel and channel not in subscribed:
                    subscribed.add(channel)
                    await websocket.send_json({"event": "subscribed", "data": {"channel": channel}})
                    # Keep lightweight: the SSE channel is primary; WebSocket proves protocol compatibility.
            else:
                await websocket.send_json({"event": "ack", "data": {"event": event}})
    except WebSocketDisconnect:
        return

