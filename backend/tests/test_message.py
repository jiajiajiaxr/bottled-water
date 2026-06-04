from typing import Any


def test_send_message_stream_endpoint_is_registered(client: Any) -> None:
    """The deprecated SSE endpoint stays registered without draining the stream."""
    routes = getattr(getattr(client, "app", None), "routes", [])
    assert any(
        getattr(route, "path", "") == "/api/v1/conversations/{conversation_id}/stream"
        and "POST" in getattr(route, "methods", set())
        for route in routes
    )
