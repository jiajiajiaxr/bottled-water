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


def test_user_can_update_profile_signature(client: Any) -> None:
    suffix = uuid.uuid4().hex[:8]
    registered = client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"signature-{suffix}@example.com",
            "username": f"signature_{suffix}",
            "display_name": "Signature User",
            "password": "Original123!",
        },
    )
    assert registered.status_code == 200, registered.text
    token = unwrap(registered.json())["access_token"]

    updated = client.patch(
        "/api/v1/auth/me",
        json={"display_name": "Signature User", "signature": "Build small, ship steady."},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert updated.status_code == 200, updated.text
    payload = unwrap(updated.json())
    assert payload["signature"] == "Build small, ship steady."

    current = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert current.status_code == 200, current.text
    assert unwrap(current.json())["signature"] == "Build small, ship steady."

