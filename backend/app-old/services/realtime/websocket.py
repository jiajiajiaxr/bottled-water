from __future__ import annotations

from fastapi import WebSocket


async def send_websocket_ack(websocket: WebSocket, event: str | None) -> None:
    await websocket.send_json({"event": "ack", "data": {"event": event}})
