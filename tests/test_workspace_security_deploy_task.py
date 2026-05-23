import uuid
from typing import Any


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


def test_workspace_project_permissions_and_audit(client: Any, auth_headers: dict[str, str]) -> None:
    permissions = client.get("/api/v1/permissions/me", headers=auth_headers)
    assert permissions.status_code == 200, permissions.text
    assert "workspace:create" in unwrap(permissions.json())["permissions"]

    workspace = client.post(
        "/api/v1/workspaces",
        json={
            "name": f"Acceptance Workspace {uuid.uuid4().hex[:8]}",
            "description": "Workspace smoke for platform-scale management",
            "type": "vertical",
            "tags": ["acceptance", "workspace"],
            "config": {"template_id": "fullstack-delivery"},
        },
        headers=auth_headers,
    )
    assert workspace.status_code == 200, workspace.text
    workspace_id = unwrap(workspace.json())["id"]

    project = client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": f"Acceptance Project {uuid.uuid4().hex[:8]}", "type": "code_project"},
        headers=auth_headers,
    )
    assert project.status_code == 200, project.text
    project_id = unwrap(project.json())["id"]

    saved = client.put(
        f"/api/v1/projects/{project_id}/files",
        json={"path": "src/main.ts", "language": "typescript", "content": "export const ok = true;"},
        headers=auth_headers,
    )
    assert saved.status_code == 200, saved.text
    assert unwrap(saved.json())["version"] == 1

    logs = client.get("/api/v1/audit-logs", headers=auth_headers)
    assert logs.status_code == 200, logs.text
    assert unwrap(logs.json())["items"]

    roles = client.get("/api/v1/security/roles", headers=auth_headers)
    assert roles.status_code == 200, roles.text
    assert unwrap(roles.json())["total"] >= 1

    users = client.get("/api/v1/security/users", headers=auth_headers)
    assert users.status_code == 200, users.text
    assert unwrap(users.json())["total"] >= 1

    stats = client.get("/api/v1/audit-logs/stats", headers=auth_headers)
    assert stats.status_code == 200, stats.text
    assert "total" in unwrap(stats.json())


def test_task_approval_and_deployment_operations(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    task = client.post(
        "/api/v1/tasks",
        json={"conversation_id": conversation_id, "title": "Build approval workflow", "description": "Create task"},
        headers=auth_headers,
    )
    assert task.status_code == 200, task.text
    task_id = unwrap(task.json())["id"]

    status = client.get(f"/api/v1/tasks/{task_id}/status", headers=auth_headers)
    assert status.status_code == 200, status.text
    assert "progress" in unwrap(status.json())

    subtasks = client.get(f"/api/v1/tasks/{task_id}/subtasks", headers=auth_headers)
    assert subtasks.status_code == 200, subtasks.text
    first_subtask = unwrap(subtasks.json())[0]

    approved = client.post(
        f"/api/v1/subtasks/{first_subtask['id']}/approve",
        json={"comment": "Looks good"},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    assert unwrap(approved.json())["status"] == "APPROVED"

    artifact = client.post(
        "/api/v1/artifacts",
        json={
            "conversation_id": conversation_id,
            "title": "Deployable Acceptance Artifact",
            "content": {"files": {"index.html": "<main>deploy</main>"}},
        },
        headers=auth_headers,
    )
    assert artifact.status_code == 200, artifact.text
    artifact_id = unwrap(artifact.json())["id"]

    deployment = client.post(
        "/api/v1/deployments",
        json={"artifact_id": artifact_id, "mode": "preview_link"},
        headers=auth_headers,
    )
    assert deployment.status_code == 200, deployment.text
    deployment_id = unwrap(deployment.json())["id"]

    logs = client.get(f"/api/v1/deployments/{deployment_id}/logs", headers=auth_headers)
    assert logs.status_code == 200, logs.text
    assert unwrap(logs.json())["items"]

    parsed = client.post("/api/v1/deployments/parse-command", json={"message": "请部署到预览链接"}, headers=auth_headers)
    assert parsed.status_code == 200, parsed.text
    assert unwrap(parsed.json())["recognized"] is True

    rollback = client.post(f"/api/v1/deployments/{deployment_id}/rollback", json={}, headers=auth_headers)
    assert rollback.status_code == 200, rollback.text
    assert unwrap(rollback.json())["status"] == "deployed"
