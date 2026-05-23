import json
import threading
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


@contextmanager
def openai_compatible_test_server() -> Any:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if self.path != "/v1/chat/completions":
                self.send_response(404)
                self.end_headers()
                return
            payload = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": body.get("model", "acceptance-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"real-compatible-ok: {body.get('messages', [{}])[-1].get('content', '')}",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
            }
            data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@contextmanager
def mcp_tool_test_server() -> Any:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            data = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"tool-ok:{body.get('params', {}).get('name')}",
                            }
                        ]
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_model_provider_config_and_real_compatible_test(client: Any, auth_headers: dict[str, str]) -> None:
    with openai_compatible_test_server() as base_url:
        created = client.post(
            "/api/v1/model-providers",
            json={
                "name": "Acceptance OpenAI Compatible",
                "provider_type": "openai-compatible",
                "base_url": base_url,
                "api_key": "test-only",
                "default_model": "acceptance-model",
                "supports_streaming": True,
            },
            headers=auth_headers,
        )
        assert created.status_code == 200, created.text
        provider = unwrap(created.json())
        assert provider["api_key_set"] is True
        assert "api_key_ref" not in provider

        model = client.post(
            "/api/v1/model-configs",
            json={
                "provider_id": provider["id"],
                "name": "Acceptance Reviewer",
                "model_id": "acceptance-reviewer",
                "purpose": "reviewer",
            },
            headers=auth_headers,
        )
        assert model.status_code == 200, model.text
        model_config = unwrap(model.json())
        assert model_config["purpose"] == "reviewer"

        tested = client.post(
            "/api/v1/model-configs/test",
            json={"model_config_id": model_config["id"], "prompt": "health check"},
            headers=auth_headers,
        )
        assert tested.status_code == 200, tested.text
        assert "real-compatible-ok: health check" in unwrap(tested.json())["response"]


def test_model_provider_config_and_mock_mode(client: Any, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/model-providers",
        json={
            "name": "Acceptance OpenAI Compatible",
            "provider_type": "openai-compatible",
            "base_url": "https://example.test/v1",
            "api_key": "mock",
            "default_model": "acceptance-model",
            "supports_streaming": True,
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    provider = unwrap(created.json())
    assert provider["api_key_set"] is True
    assert "api_key_ref" not in provider

    model = client.post(
        "/api/v1/model-configs",
        json={
            "provider_id": provider["id"],
            "name": "Acceptance Reviewer",
            "model_id": "acceptance-reviewer",
            "purpose": "reviewer",
        },
        headers=auth_headers,
    )
    assert model.status_code == 200, model.text
    model_config = unwrap(model.json())
    assert model_config["purpose"] == "reviewer"

    tested = client.post(
        "/api/v1/model-configs/test",
        json={"model_config_id": model_config["id"], "prompt": "health check"},
        headers=auth_headers,
    )
    assert tested.status_code == 200, tested.text
    assert "response" in unwrap(tested.json())


def test_custom_agent_can_bind_model_config_and_use_it_for_test(client: Any, auth_headers: dict[str, str]) -> None:
    created = client.post(
        "/api/v1/model-providers",
        json={
            "name": f"Agent Bound Provider {uuid.uuid4().hex[:8]}",
            "provider_type": "openai-compatible",
            "base_url": "https://example.test/v1",
            "api_key": "mock",
            "default_model": "agent-bound-model",
            "supports_streaming": True,
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    provider = unwrap(created.json())

    model = client.post(
        "/api/v1/model-configs",
        json={
            "provider_id": provider["id"],
            "name": "Agent Bound Worker",
            "model_id": "agent-bound-worker",
            "purpose": "worker",
        },
        headers=auth_headers,
    )
    assert model.status_code == 200, model.text
    model_config = unwrap(model.json())

    agent_name = f"acceptance-agent-{uuid.uuid4().hex[:8]}"
    agent = client.post(
        "/api/v1/agents",
        json={
            "name": agent_name,
            "description": "Agent with editable bottom model",
            "capabilities": [{"label": "test", "category": "qa", "proficiency": 4}],
            "system_prompt": "You are a test worker.",
            "tools": ["file_read"],
            "config": {"model_config_id": model_config["id"], "temperature": 0.2},
        },
        headers=auth_headers,
    )
    assert agent.status_code == 200, agent.text
    agent_body = unwrap(agent.json())
    assert agent_body["config"]["model_config_id"] == model_config["id"]

    tested = client.post(
        f"/api/v1/agents/{agent_body['id']}/test",
        json={"message": "agent health check"},
        headers=auth_headers,
    )
    assert tested.status_code == 200, tested.text
    tested_body = unwrap(tested.json())
    assert tested_body["model"] == "agent-bound-worker"
    assert "agent health check" in tested_body["response"]


def test_mcp_sandbox_and_remote_control(
    client: Any,
    auth_headers: dict[str, str],
) -> None:
    workspace = client.post(
        "/api/v1/workspaces",
        json={"name": f"Acceptance MCP Workspace {uuid.uuid4().hex[:8]}", "description": "control plane smoke", "type": "custom"},
        headers=auth_headers,
    )
    assert workspace.status_code == 200, workspace.text
    workspace_id = unwrap(workspace.json())["id"]

    mcp = client.post(
        "/api/v1/mcp-servers",
        json={
            "workspace_id": workspace_id,
            "name": "Acceptance Filesystem MCP",
            "transport": "stdio",
            "command": "agenthub-mcp-filesystem",
            "args": ["--root", "."],
            "tool_filter": ["file.*", "sandbox.*"],
            "retry": 1,
        },
        headers=auth_headers,
    )
    assert mcp.status_code == 200, mcp.text
    server_id = unwrap(mcp.json())["id"]

    probed = client.post(f"/api/v1/mcp-servers/{server_id}/probe", headers=auth_headers)
    assert probed.status_code == 200, probed.text
    assert unwrap(probed.json())["health_status"] == "online"

    sandbox = client.post(
        "/api/v1/sandboxes",
        json={"workspace_id": workspace_id, "name": "Acceptance Sandbox", "image": "python:3.11-slim"},
        headers=auth_headers,
    )
    assert sandbox.status_code == 200, sandbox.text
    sandbox_id = unwrap(sandbox.json())["id"]

    command = client.post(
        f"/api/v1/sandboxes/{sandbox_id}/commands",
        json={"command": "python --version", "timeout_seconds": 5},
        headers=auth_headers,
    )
    assert command.status_code == 200, command.text
    result = unwrap(command.json())["result"]
    assert result["exit_code"] == 0
    assert "python --version" in result["stdout"]

    remote = client.post(
        "/api/v1/remote-connections",
        json={
            "workspace_id": workspace_id,
            "name": "Acceptance Browser",
            "connection_type": "browser",
            "endpoint": "http://127.0.0.1:5173",
            "capabilities": ["open", "screenshot"],
        },
        headers=auth_headers,
    )
    assert remote.status_code == 200, remote.text
    remote_id = unwrap(remote.json())["id"]

    connected = client.post(f"/api/v1/remote-connections/{remote_id}/connect", headers=auth_headers)
    assert connected.status_code == 200, connected.text
    assert unwrap(connected.json())["status"] == "connected"


def test_real_mcp_tool_invocation_chain(client: Any, auth_headers: dict[str, str]) -> None:
    with mcp_tool_test_server() as url:
        created = client.post(
            "/api/v1/mcp-servers",
            json={
                "name": "Acceptance HTTP MCP",
                "transport": "httpStream",
                "url": url,
                "tool_filter": ["echo.*"],
            },
            headers=auth_headers,
        )
        assert created.status_code == 200, created.text
        server = unwrap(created.json())

        invoked = client.post(
            f"/api/v1/mcp-servers/{server['id']}/tools/echo.ping/invoke",
            json={"arguments": {"input": "hello"}},
            headers=auth_headers,
        )
        assert invoked.status_code == 200, invoked.text
        invocation = unwrap(invoked.json())
        assert invocation["status"] == "succeeded"
        assert invocation["result"]["result"]["content"][0]["text"] == "tool-ok:echo.ping"

        history = client.get("/api/v1/mcp-invocations", headers=auth_headers)
        assert history.status_code == 200, history.text
        assert unwrap(history.json())["total"] >= 1


def test_message_attachments_are_stored_for_agent_context(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    upload = client.post(
        "/api/v1/files",
        files={"file": ("requirements.txt", b"Build a dashboard with artifact preview.", "text/plain")},
        data={"conversation_id": conversation_id, "purpose": "attachment"},
        headers=auth_headers,
    )
    assert upload.status_code == 200, upload.text
    file_asset = unwrap(upload.json())

    message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={
            "client_message_id": "attachment-context-test",
            "content_type": "text",
            "content": {
                "text": "Read the uploaded requirements and continue.",
                "attachments": [{"file_id": file_asset["file_id"]}],
            },
        },
        headers=auth_headers,
    )
    assert message.status_code == 200, message.text
    body = unwrap(message.json())
    attachments = body["rawContent"]["attachments"]
    assert attachments[0]["filename"] == "requirements.txt"
    assert "dashboard" in attachments[0]["extracted_text"]
