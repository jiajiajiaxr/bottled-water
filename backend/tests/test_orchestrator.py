from typing import Any


def test_orchestrator_accepts_task_request(
    client: Any,
    api_paths: dict[str, str],
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    response = client.post(
        api_paths["orchestrator_tasks"],
        json={
            "conversation_id": conversation_id,
            "prompt": "Build a todo app preview with add and complete actions.",
        },
        headers=auth_headers,
    )

    assert response.status_code in {200, 201, 202}, response.text
    body = response.json()
    assert body.get("id") or body.get("task_id") or body.get("status")
