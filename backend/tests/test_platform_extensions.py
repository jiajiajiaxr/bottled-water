import uuid
from typing import Any


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


def test_agent_config_and_group_members(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    created = client.post(
        "/api/v1/agents",
        json={
            "name": f"Acceptance Config Agent {uuid.uuid4().hex[:8]}",
            "type": "custom",
            "description": "Handles acceptance extension checks",
            "capabilities": ["acceptance", "configuration"],
            "system_prompt": "Be precise.",
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    agent = unwrap(created.json())
    agent_id = agent["id"]

    updated = client.patch(
        f"/api/v1/agents/{agent_id}",
        json={"config": {"temperature": 0.2}, "tools": ["search"]},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert unwrap(updated.json())["config"]["temperature"] == 0.2

    added = client.post(
        f"/api/v1/conversations/{conversation_id}/members",
        json={"agent_ids": [agent_id], "role": "member"},
        headers=auth_headers,
    )
    assert added.status_code == 200, added.text
    participants = unwrap(added.json())["participants"]
    assert any(item.get("agent_id") == agent_id for item in participants)


def test_file_upload_and_knowledge_base(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    upload = client.post(
        "/api/v1/files",
        files={"file": ("notes.txt", b"AgentHub knowledge retrieval acceptance note.", "text/plain")},
        data={"conversation_id": conversation_id, "purpose": "attachment"},
        headers=auth_headers,
    )
    assert upload.status_code == 200, upload.text
    file_asset = unwrap(upload.json())
    assert file_asset["file_id"]
    assert file_asset["size"] > 0

    created = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "Acceptance KB", "description": "API contract smoke"},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    kb_id = unwrap(created.json())["id"]

    document = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        json={
            "title": "Retrieval Note",
            "content": "AgentHub retrieves uploaded and manual knowledge for agents.",
        },
        headers=auth_headers,
    )
    assert document.status_code == 200, document.text
    assert unwrap(document.json())["index_status"] == "indexed"

    retrieved = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/retrieve",
        json={"query": "AgentHub knowledge", "top_k": 3},
        headers=auth_headers,
    )
    assert retrieved.status_code == 200, retrieved.text
    assert unwrap(retrieved.json())["items"]
