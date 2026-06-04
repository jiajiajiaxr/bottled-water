import { useEffect, useState } from "react";
import {
  App as AntApp,
  Avatar,
  Card,
  Divider,
  List,
  Space,
  Statistic,
  Table,
  Tag,
} from "antd";
import { api } from "@/api";
import { formatTime } from "@/lib/format";
import type { AuditLog, SecurityRole, SecurityUser } from "@/types";

export function SecurityPanel() {
  const { message } = AntApp.useApp();
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [securityRoles, setSecurityRoles] = useState<SecurityRole[]>([]);
  const [securityUsers, setSecurityUsers] = useState<SecurityUser[]>([]);
  const [auditStats, setAuditStats] = useState<{
    total: number;
    high_risk: number;
    by_action: Record<string, number>;
  }>();

  const load = async () => {
    try {
      const [logs, roles, users, stats] = await Promise.all([
        api.auditLogs().catch(() => []),
        api.securityRoles().catch(() => []),
        api.securityUsers().catch(() => []),
        api.auditStats().catch(() => undefined),
      ]);
      setAuditLogs(logs);
      setSecurityRoles(roles);
      setSecurityUsers(users);
      setAuditStats(stats);
    } catch {
      message.error("加载安全数据失败");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="workspace-grid">
      <Card title="Audit">
        <Space className="mb-8" wrap>
          <Statistic
            title="Events"
            value={auditStats?.total ?? auditLogs.length}
          />
          <Statistic
            title="High risk"
            value={auditStats?.high_risk ?? 0}
          />
        </Space>
        <Table
          size="small"
          rowKey="id"
          dataSource={auditLogs}
          pagination={{ pageSize: 6 }}
          columns={[
            { title: "Action", dataIndex: "action" },
            {
              title: "Target",
              render: (_, row: AuditLog) =>
                `${row.target_type}:${row.target_id ?? "-"}`,
            },
            { title: "Risk", dataIndex: "risk_score" },
            {
              title: "Time",
              dataIndex: "created_at",
              render: (value?: string) => formatTime(value),
            },
          ]}
        />
      </Card>
      <Card title="Roles and users">
        <List
          size="small"
          dataSource={securityRoles}
          renderItem={(role) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <strong>{role.code}</strong>
                    <Tag>{role.permissions.length} perms</Tag>
                  </Space>
                }
                description={role.description}
              />
            </List.Item>
          )}
        />
        <Divider />
        <List
          size="small"
          dataSource={securityUsers}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                avatar={
                  <Avatar>{item.display_name.slice(0, 1)}</Avatar>
                }
                title={
                  <Space>
                    <strong>{item.display_name}</strong>
                    <Tag>{item.role}</Tag>
                  </Space>
                }
                description={`${item.email} · ${item.roles.join(", ") || "ROLE_USER"}`}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
