from typing import Any


def test_send_message_to_conversation(
    client: Any,
    api_paths: dict[str, str],
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    """测试 SSE 流式端点（deprecated，保留兼容）。

    注意：/stream 返回 SSE EventSourceResponse，流式响应由 WebSocket 端点完整覆盖。
    此处仅验证端点可达且认证正常。
    """
    path = f"/api/v1/conversations/{conversation_id}/stream"
    response = client.post(
        path,
        json={
            "content": {"text": "Create a simple dashboard preview."},
        },
        headers=auth_headers,
    )

    # SSE 流式端点返回 200（EventSourceResponse 会持续推送直到 session 完成）
    # 注意：流式响应非 JSON，直接检查状态码即可
    assert response.status_code == 200, response.text
