import uuid
from typing import Any


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


def test_user_can_register_login_and_change_password(client: Any) -> None:
    suffix = uuid.uuid4().hex[:8]
    email = f"register-{suffix}@example.com"
    username = f"register_{suffix}"

    registered = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "username": username,
            "display_name": "Register Acceptance",
            "password": "Original123!",
        },
    )
    assert registered.status_code == 200, registered.text
    payload = unwrap(registered.json())
    token = payload["access_token"]
    assert payload["user"]["name"] == "Register Acceptance"

    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": "Original123!", "new_password": "Changed123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert changed.status_code == 200, changed.text
    assert unwrap(changed.json())["changed"] is True

    old_login = client.post("/api/v1/auth/login", json={"email": email, "password": "Original123!"})
    assert old_login.status_code == 401

    new_login = client.post("/api/v1/auth/login", json={"email": email, "password": "Changed123!"})
    assert new_login.status_code == 200, new_login.text

