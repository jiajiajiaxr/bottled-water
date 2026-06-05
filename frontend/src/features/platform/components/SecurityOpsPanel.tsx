import {
  App as AntApp,
  Avatar,
  Button,
  Card,
  Divider,
  List,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { useMemo, useState } from "react";
import { api } from "@/api";
import { formatTime } from "@/lib/format";
import type { AuditLog, SecurityRole, SecurityUser } from "@/types";

const { Text } = Typography;

interface SecurityOpsPanelProps {
  auditLogs: AuditLog[];
  auditStats?: {
    total: number;
    high_risk: number;
    by_action: Record<string, number>;
  };
  roles: SecurityRole[];
  users: SecurityUser[];
  onRefresh: () => Promise<void>;
}

interface RoleOption {
  label: string;
  value: string;
  roleCode: string;
}

function roleValue(roleCode: string) {
  const raw = roleCode.replace(/^ROLE_/i, "").toLowerCase();
  return raw === "user" ? "member" : raw;
}

function roleLabel(role: SecurityRole) {
  return role.name || role.code.replace(/^ROLE_/i, "");
}

function auditDetail(detail: Record<string, unknown>) {
  if (!detail || Object.keys(detail).length === 0) return "无附加详情";
  return JSON.stringify(detail, null, 2);
}

export function SecurityOpsPanel({
  auditLogs,
  auditStats,
  roles,
  users,
  onRefresh,
}: SecurityOpsPanelProps) {
  const { message } = AntApp.useApp();
  const [updatingUserId, setUpdatingUserId] = useState<string>();

  const roleOptions = useMemo<RoleOption[]>(
    () =>
      roles.map((role) => ({
        label: roleLabel(role),
        value: roleValue(role.code),
        roleCode: role.code,
      })),
    [roles],
  );

  const updateUserRole = async (user: SecurityUser, nextRole: string) => {
    if (nextRole === user.role) return;
    setUpdatingUserId(user.id);
    try {
      await api.updateSecurityUserRole(user.id, nextRole);
      await onRefresh();
      message.success(`${user.display_name} 的角色已更新`);
    } catch (error) {
      message.error(
        error instanceof Error ? error.message : "角色更新失败，请稍后重试",
      );
    } finally {
      setUpdatingUserId(undefined);
    }
  };

  return (
    <div className="workspace-grid">
      <Card title="审计日志">
        <Space className="mb-8" wrap>
          <Statistic title="事件总数" value={auditStats?.total ?? auditLogs.length} />
          <Statistic title="高风险事件" value={auditStats?.high_risk ?? 0} />
        </Space>
        <Table
          size="small"
          rowKey="id"
          dataSource={auditLogs}
          pagination={{ pageSize: 6 }}
          expandable={{
            expandedRowRender: (row) => (
              <pre className="audit-detail-preview">{auditDetail(row.detail)}</pre>
            ),
          }}
          columns={[
            { title: "动作", dataIndex: "action" },
            {
              title: "目标",
              render: (_, row: AuditLog) =>
                `${row.target_type}:${row.target_id ?? "-"}`,
            },
            {
              title: "风险",
              dataIndex: "risk_score",
              render: (value: number) => (
                <Tag color={value >= 7 ? "red" : value >= 4 ? "orange" : "blue"}>
                  {value}
                </Tag>
              ),
            },
            {
              title: "时间",
              dataIndex: "created_at",
              render: (value?: string) => formatTime(value),
            },
          ]}
        />
      </Card>
      <Card title="角色与用户">
        <List
          size="small"
          dataSource={roles}
          renderItem={(role) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space>
                    <strong>{role.code}</strong>
                    <Tag>{role.permissions.length} 项权限</Tag>
                    {role.is_system ? <Tag color="blue">系统角色</Tag> : null}
                  </Space>
                }
                description={role.description || "暂无说明"}
              />
            </List.Item>
          )}
        />
        <Divider />
        <List
          size="small"
          dataSource={users}
          renderItem={(item) => (
            <List.Item
              actions={[
                <Select
                  key="role"
                  aria-label={`${item.display_name} 角色`}
                  data-testid={`security-user-role-${item.id}`}
                  value={item.role}
                  loading={updatingUserId === item.id}
                  disabled={updatingUserId === item.id || roleOptions.length === 0}
                  options={roleOptions}
                  popupMatchSelectWidth={180}
                  style={{ width: 150 }}
                  onChange={(nextRole) => updateUserRole(item, nextRole)}
                />,
              ]}
            >
              <List.Item.Meta
                avatar={<Avatar>{item.display_name.slice(0, 1)}</Avatar>}
                title={
                  <Space wrap>
                    <strong>{item.display_name}</strong>
                    <Tag>{item.role}</Tag>
                    <Text type="secondary">{item.status}</Text>
                  </Space>
                }
                description={`${item.email} · ${
                  item.roles.join(", ") || "ROLE_USER"
                }`}
              />
            </List.Item>
          )}
        />
        <Button className="mt-8" onClick={onRefresh} loading={Boolean(updatingUserId)}>
          刷新安全数据
        </Button>
      </Card>
    </div>
  );
}
