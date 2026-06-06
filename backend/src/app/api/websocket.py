"""WebSocket 异步对话接口

提供 conversation 级别的 WebSocket 端点，支持：
- 双向实时通信
- 用户随时发送消息（chat.send）
- 随时取消 generation（chat.cancel）
- 心跳保活（ping/pong）

事件统一通过 WebSocketSink 推送，SSE 端点保留兼容。
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_runtime.core.types import Event as RuntimeEvent
from app.core.errors import NotFoundError, UnauthorizedError, ValidationAppError
from app.core.security import decode_access_token
from app.events import WebSocketSink
from db.models import Conversation, FileAsset, Message, User, utcnow
from db.session import AsyncSessionLocal
from app.services.conversation_session_manager import (
    ConversationSessionManager,
)
from app.services.chat.scheduling import persist_scheduling_strategy, resolve_scheduling_strategy
from app.services.chat.message_prompt import runtime_prompt_for_message
from common.logger import get_logger

logger = get_logger("app.api.websocket")

router = APIRouter(tags=["websocket"])


async def _authenticate_ws(token: str) -> User:
    """WebSocket 认证（手动实现，不使用 FastAPI Dependency）。"""
    if not token:
        raise UnauthorizedError()
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise UnauthorizedError("Token 无效或已过期")

    async with AsyncSessionLocal() as db:
        user = await db.get(User, payload["sub"])
        if not user or user.deleted_at is not None:
            raise UnauthorizedError("用户不存在或已停用")
        return user


async def _get_conversation_ws(db: AsyncSession, user: User, conversation_id: str) -> Conversation:
    """获取 conversation（WebSocket 专用版本）。"""
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.creator_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    return conversation


def _message_text(payload: dict) -> str:
    """从 payload 中提取消息文本。"""
    content = payload.get("content")
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    if isinstance(content, str):
        return content
    return str(payload.get("prompt") or "")


async def _save_user_message(
    db: AsyncSession,
    user: User,
    conversation: Conversation,
    data: dict,
) -> Message:
    """保存用户消息到数据库（WebSocket 路径，不触发旧 SSE 编排）。"""
    text = _message_text(data).strip()
    if not text:
        raise ValidationAppError("消息内容不能为空")

    raw_content = data.get("content") if isinstance(data.get("content"), dict) else {}
    attachments = raw_content.get("attachments") or data.get("attachments") or []
    normalized_attachments: list[dict] = []

    for item in attachments:
        file_id = item.get("file_id") or item.get("id") if isinstance(item, dict) else str(item)
        if not file_id:
            continue

        file_asset = await db.scalar(
            select(FileAsset).where(
                FileAsset.id == file_id,
                FileAsset.owner_id == user.id,
                FileAsset.deleted_at.is_(None),
            )
        )
        if file_asset:
            if file_asset.conversation_id and file_asset.conversation_id != conversation.id:
                logger.warning(
                    "拒绝跨会话附件引用",
                    file_id=file_asset.id,
                    source_conversation_id=file_asset.conversation_id,
                    target_conversation_id=conversation.id,
                    user_id=user.id,
                )
                continue
            if not file_asset.conversation_id:
                file_asset.conversation_id = conversation.id
            normalized_attachments.append(
                {
                    "file_id": file_asset.id,
                    "filename": file_asset.original_filename,
                    "content_type": file_asset.content_type,
                    "size": file_asset.size,
                    "parse_status": file_asset.parse_status,
                    "extracted_text": (file_asset.extracted_text or "")[:12000],
                    "metadata": file_asset.extra or {},
                }
            )

    # 调度策略
    scheduling_strategy = resolve_scheduling_strategy(conversation, data.get("scheduling_strategy"))
    if data.get("scheduling_strategy"):
        persist_scheduling_strategy(conversation, scheduling_strategy)

    message = Message(
        client_message_id=data.get("client_message_id") or str(uuid.uuid4()),
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        sender_avatar_url=user.avatar_url,
        content_type=data.get("content_type") or "text",
        content={"text": text, "attachments": normalized_attachments},
        status="sent",
        reply_to_message_id=data.get("reply_to_message_id") or data.get("quotedMessageId"),
        extra={
            "thinking_enabled": bool(data.get("thinking_enabled")),
            "scheduling_strategy": scheduling_strategy,
            "model_config_id": data.get("model_config_id"),
        },
    )

    conversation.last_message_preview = text[:300]
    conversation.last_message_sender = user.display_name
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 5)
    conversation.message_count += 1

    db.add(message)
    await db.commit()
    await db.refresh(message)

    return message


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_websocket(
    websocket: WebSocket,
    conversation_id: str,
    token: str = Query(...),
) -> None:
    """Conversation 级 WebSocket 端点。

    协议：
    - 连接建立后发送认证成功的 confirmation（可选）
    - 客户端发送 JSON 消息：{"event": "chat.send", "data": {...}, "request_id": "..."}
    - 服务端推送 JSON 事件：{"event": "agent.token", "data": {...}, "request_id": "..."}

    客户端事件：
    - chat.send: 发送用户消息
    - chat.cancel: 取消当前 generation
    - ping: 心跳

    服务端事件：
    - chat.ack: 消息已接收
    - chat.cancelled: 取消确认
    - pong: 心跳响应
    - 所有运行时事件（system.session_started, agent.token, ...）
    """
    # 1. 认证
    try:
        user = await _authenticate_ws(token)
    except UnauthorizedError as e:
        await websocket.close(code=4001, reason=str(e))
        return

    await websocket.accept()
    logger.info("WebSocket 连接", conversation_id=conversation_id, user_id=user.id)

    # 2. 注册 WebSocketSink
    sink = WebSocketSink(conversation_id)
    sink.register(websocket)

    session_manager = ConversationSessionManager.get_instance()

    try:
        while True:
            msg = await websocket.receive_text()
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "data": {"message": "JSON 格式错误"}})
                continue

            event_type = payload.get("event")
            data = payload.get("data") or {}
            request_id = payload.get("request_id")

            if event_type == "chat.send":
                await _handle_chat_send(
                    websocket, conversation_id, user, data, request_id, sink, session_manager
                )

            elif event_type == "chat.cancel":
                await _handle_chat_cancel(websocket, conversation_id, request_id, session_manager)

            elif event_type == "ping":
                await websocket.send_json({"event": "pong", "data": {}})

            else:
                await websocket.send_json(
                    {
                        "event": "error",
                        "data": {"message": f"未知事件类型: {event_type}"},
                        "request_id": request_id,
                    }
                )

    except WebSocketDisconnect:
        logger.info("WebSocket 断开", conversation_id=conversation_id, user_id=user.id)
    except Exception as e:
        logger.error("WebSocket 异常", conversation_id=conversation_id, error=str(e))
    finally:
        sink.unregister(websocket)
        # Session 继续运行，不关闭


async def _handle_chat_send(
    websocket: WebSocket,
    conversation_id: str,
    user: User,
    data: dict,
    request_id: str | None,
    sink: WebSocketSink,
    session_manager: ConversationSessionManager,
) -> None:
    """处理 chat.send 事件。"""
    async with AsyncSessionLocal() as db:
        try:
            conversation = await _get_conversation_ws(db, user, conversation_id)
            message = await _save_user_message(db, user, conversation, data)

            # 获取或创建 Session（第一次消息时创建，后续复用）
            await session_manager.get_or_create_session(
                db,
                conversation,
                model_config_id=data.get("model_config_id"),
                event_sink=sink,
            )

            # 异步发送用户输入（不阻塞 WS 循环）
            content = (
                message.content.get("text", "")
                if isinstance(message.content, dict)
                else str(message.content)
            )
            runtime_content = runtime_prompt_for_message(message)
            asyncio.create_task(
                _send_user_input_async(session_manager, conversation_id, content, runtime_content),
                name=f"ws-send-{conversation_id}",
            )

            await websocket.send_json(
                {
                    "event": "chat.ack",
                    "data": {"message_id": str(message.id), "content_preview": content[:100]},
                    "request_id": request_id,
                }
            )

        except Exception as e:
            logger.error("chat.send 处理失败", conversation_id=conversation_id, error=str(e))
            await websocket.send_json(
                {
                    "event": "error",
                    "data": {"message": str(e)},
                    "request_id": request_id,
                }
            )


async def _send_user_input_async(
    session_manager: ConversationSessionManager,
    conversation_id: str,
    content: str,
    runtime_content: str | None = None,
) -> None:
    """异步发送用户输入到 Session（后台任务）。"""
    try:
        await session_manager.send_user_input(
            conversation_id,
            content,
            runtime_content=runtime_content,
        )
    except Exception as e:
        await WebSocketSink(conversation_id).emit(
            RuntimeEvent(
                type="generation:failed",
                payload={
                    "conversation_id": conversation_id,
                    "status": "failed",
                    "error": str(e),
                },
            )
        )
        logger.error("发送用户输入失败", conversation_id=conversation_id, error=str(e))


async def _handle_chat_cancel(
    websocket: WebSocket,
    conversation_id: str,
    request_id: str | None,
    session_manager: ConversationSessionManager,
) -> None:
    """处理 chat.cancel 事件。"""
    try:
        cancelled = await session_manager.cancel_generation(conversation_id)
        await websocket.send_json(
            {
                "event": "chat.cancelled",
                "data": {"cancelled": cancelled},
                "request_id": request_id,
            }
        )
    except Exception as e:
        logger.error("chat.cancel 处理失败", conversation_id=conversation_id, error=str(e))
        await websocket.send_json(
            {
                "event": "error",
                "data": {"message": str(e)},
                "request_id": request_id,
            }
        )


# 保留旧的全局 WS 端点（协议兼容性验证）
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """全局 WebSocket 端点（保留用于协议兼容性验证）。"""
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
            else:
                await websocket.send_json({"event": "ack", "data": {"event": event}})
    except WebSocketDisconnect:
        return
