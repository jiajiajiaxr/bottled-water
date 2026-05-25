from typing import Any


def test_signup_login_and_me(
    client: Any,
    api_paths: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    response = client.get(api_paths["me"], headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("email") or body.get("id") or body.get("user")


def test_protected_endpoint_rejects_anonymous(
    client: Any,
    api_paths: dict[str, str],
) -> None:
    response = client.get(api_paths["me"])

    assert response.status_code in {401, 403}, response.text
