from typing import Any


def test_send_message_to_conversation(
    client: Any,
    api_paths: dict[str, str],
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    path = api_paths["messages"].format(conversation_id=conversation_id)
    response = client.post(
        path,
        json={
            "conversation_id": conversation_id,
            "content": "Create a simple dashboard preview.",
            "role": "user",
        },
        headers=auth_headers,
    )

    assert response.status_code in {200, 201, 202}, response.text
    body = response.json()
    assert body.get("id") or body.get("message_id")
