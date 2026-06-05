import React from "react";
import { App as AntApp } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import { SecurityOpsPanel } from "../src/features/platform/components/SecurityOpsPanel";
import type { AuditLog, SecurityRole, SecurityUser } from "../src/types";

vi.mock("../src/api", () => ({
  api: {
    updateSecurityUserRole: vi.fn(),
  },
}));

const roles: SecurityRole[] = [
  {
    id: "role-user",
    code: "ROLE_USER",
    name: "普通用户",
    description: "基础访问权限",
    is_system: true,
    permissions: [],
  },
  {
    id: "role-developer",
    code: "ROLE_DEVELOPER",
    name: "开发者",
    description: "可管理工具和 MCP",
    is_system: true,
    permissions: [
      {
        id: "perm-1",
        code: "tool:write",
        resource: "tool",
        action: "write",
      },
    ],
  },
];

const users: SecurityUser[] = [
  {
    id: "user-1",
    email: "demo@example.com",
    username: "demo",
    display_name: "演示用户",
    role: "member",
    status: "active",
    roles: ["ROLE_USER"],
  },
];

const logs: AuditLog[] = [
  {
    id: "audit-1",
    action: "security.user.role.update",
    target_type: "user",
    target_id: "user-1",
    risk_score: 3,
    detail: { role: "developer" },
    created_at: "2026-06-04T08:00:00Z",
  },
];

describe("SecurityOpsPanel", () => {
  it("updates user role and refreshes security data", async () => {
    const refresh = vi.fn(async () => undefined);
    vi.mocked(api.updateSecurityUserRole).mockResolvedValue({
      ...users[0],
      role: "developer",
      roles: ["ROLE_USER", "ROLE_DEVELOPER"],
    });

    render(
      <AntApp>
        <SecurityOpsPanel
          auditLogs={logs}
          auditStats={{ total: 1, high_risk: 0, by_action: {} }}
          roles={roles}
          users={users}
          onRefresh={refresh}
        />
      </AntApp>,
    );

    expect(screen.getByText("审计日志")).toBeInTheDocument();
    expect(screen.getByText("角色与用户")).toBeInTheDocument();

    const roleSelect = screen.getByTestId("security-user-role-user-1");
    const selector = roleSelect.querySelector(".ant-select-selector");
    expect(selector).not.toBeNull();
    fireEvent.mouseDown(selector as Element);
    fireEvent.click(await screen.findByText("开发者"));

    await waitFor(() =>
      expect(api.updateSecurityUserRole).toHaveBeenCalledWith(
        "user-1",
        "developer",
      ),
    );
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
