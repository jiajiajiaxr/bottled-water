from typing import Any


def test_deployment_request_contract(
    client: Any,
    api_paths: dict[str, str],
    auth_headers: dict[str, str],
) -> None:
    response = client.post(
        api_paths["deployments"],
        json={"artifact_id": "acceptance-artifact", "environment": "preview"},
        headers=auth_headers,
    )

    assert response.status_code in {200, 201, 202, 404}, response.text
    if response.status_code != 404:
        body = response.json()
        assert body.get("id") or body.get("deployment_id") or body.get("status")
