"""测试 WebSocket 端点（/ws/conversations/{conversation_id}）

注意：完整 WebSocket 测试需要真实的 WS 连接，这里仅验证端点注册和基本路由。
"""

import pytest


class TestWebSocketEndpointRegistered:
    """测试 WebSocket 端点已注册"""

    def test_websocket_endpoint_exists_in_app(self, client):
        """验证 /ws/conversations/{id} 端点存在于应用中。

        WebSocket 端点的真实测试需要单独的服务进程或 WebSocket 测试工具。
        这里验证路由已正确注册。
        """
        # 获取 app 的 routes 列表，验证 websocket 路由已注册
        from app.main import app
        routes = [r.path for r in app.routes]
        assert any("/ws/conversations/" in r for r in routes)