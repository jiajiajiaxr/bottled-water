import { useEffect, useMemo, useState } from "react";
import {
  ApiOutlined,
  CodeOutlined,
  ReloadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Card,
  Empty,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { api } from "@/api";
import type { ExternalAgentProbe, ExternalAgentRun } from "@/types";

const { Text } = Typography;

const PROVIDER_LABELS: Record<string, string> = {
  codex: "Codex CLI",
  claude_code: "Claude Code CLI",
  opencode: "OpenCode CLI",
};

export function ExternalAgentsPanel() {
  const { message } = AntApp.useApp();
  const [probes, setProbes] = useState<ExternalAgentProbe[]>([]);
  const [runs, setRuns] = useState<ExternalAgentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [probing, setProbing] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [probeResult, recentRuns] = await Promise.all([
        api.externalAgentProbe(),
        api.externalAgentRuns(undefined, 20),
      ]);
      setProbes(probeResult.providers);
      setRuns(recentRuns);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "加载外部 Agent 状态失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleProbe = async (provider: string) => {
    setProbing(provider);
    try {
      const result = await api.reprobeExternalAgent(provider);
      setProbes((current) => mergeProbeResults(current, result.providers));
      message.success(`${providerLabel(provider)} 探测完成`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "探测失败");
    } finally {
      setProbing(null);
    }
  };

  return (
    <Space className="external-agents-panel" direction="vertical" size={16}>
      <Card
        title="调用外部智能体"
        extra={
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={load}
          >
            刷新
          </Button>
        }
      >
        <Text type="secondary">
          Codex / Claude Code / OpenCode 通过统一适配网关接入。Agent 获得
          external_agent.invoke 工具权限后，可按 provider 启动、探测、查询或取消外部智能体运行。
        </Text>
        <ExternalAgentStatusCards
          probes={probes}
          probing={probing}
          onProbe={handleProbe}
        />
      </Card>
      <Card title="最近运行记录">
        <ExternalAgentRunsTable loading={loading} runs={runs} />
      </Card>
    </Space>
  );
}

export function ExternalAgentStatusCards({
  probes,
  probing,
  onProbe,
}: {
  probes: ExternalAgentProbe[];
  probing: string | null;
  onProbe: (provider: string) => void;
}) {
  const items = useMemo(
    () =>
      ["codex", "claude_code", "opencode"].map(
        (provider) =>
          probes.find((item) => item.provider === provider) ?? {
            provider,
            installed: false,
            reason: "not_probed",
            setup_hint: "点击探测以检查本机 CLI 状态。",
          },
      ),
    [probes],
  );

  return (
    <div className="external-agent-status-grid">
      {items.map((probe) => (
        <Card className="external-agent-status-card" key={probe.provider}>
          <Space align="start" size={12}>
            <span className="external-agent-status-icon">
              {probe.provider === "codex" ? <CodeOutlined /> : <ApiOutlined />}
            </span>
            <Space direction="vertical" size={6}>
              <Space wrap>
                <Text strong>{providerLabel(probe.provider)}</Text>
                <Tag color={probe.installed ? "green" : "orange"}>
                  {probe.installed ? "可用" : "降级"}
                </Tag>
              </Space>
              <Text type="secondary">
                命令来源：{probe.command_source || "未探测"}
              </Text>
              <Text className="external-agent-command" ellipsis>
                {commandProbeSummary(probe)}
              </Text>
              {!probe.installed && (
                <Text type="warning">
                  <WarningOutlined /> {probe.setup_hint || "当前环境未找到 CLI。"}
                </Text>
              )}
              <Space wrap>
                {(probe.capabilities ?? []).slice(0, 4).map((capability) => (
                  <Tag key={capability}>{capability}</Tag>
                ))}
              </Space>
              <Button
                size="small"
                loading={probing === probe.provider}
                onClick={() => onProbe(probe.provider)}
              >
                重新探测
              </Button>
            </Space>
          </Space>
        </Card>
      ))}
    </div>
  );
}

export function ExternalAgentRunsTable({
  loading,
  runs,
}: {
  loading: boolean;
  runs: ExternalAgentRun[];
}) {
  const columns: ColumnsType<ExternalAgentRun> = [
    {
      title: "Provider",
      dataIndex: "provider",
      width: 150,
      render: (value: string) => providerLabel(value),
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 120,
      render: (value: string) => (
        <Tag color={statusColor(value)}>{value || "unknown"}</Tag>
      ),
    },
    {
      title: "Run ID",
      dataIndex: "run_id",
      ellipsis: true,
    },
    {
      title: "变更文件",
      dataIndex: "changed_files",
      width: 110,
      render: (value: unknown[]) => value?.length ?? 0,
    },
    {
      title: "耗时",
      dataIndex: "duration_ms",
      width: 100,
      render: (value?: number | null) => (value ? `${value} ms` : "-"),
    },
    {
      title: "错误",
      dataIndex: "error",
      ellipsis: true,
      render: (value?: string | null) => value || "-",
    },
  ];

  if (!loading && !runs.length) {
    return <Empty description="暂无外部 Agent 运行记录" />;
  }

  return (
    <Table
      columns={columns}
      dataSource={runs}
      loading={loading}
      pagination={false}
      rowKey="run_id"
      size="small"
    />
  );
}

function mergeProbeResults(
  current: ExternalAgentProbe[],
  incoming: ExternalAgentProbe[],
) {
  const byProvider = new Map<string, ExternalAgentProbe>();
  current.forEach((item) => byProvider.set(item.provider, item));
  incoming.forEach((item) => byProvider.set(item.provider, item));
  return Array.from(byProvider.values());
}

function providerLabel(provider: string) {
  return PROVIDER_LABELS[provider] ?? provider;
}

function commandProbeSummary(probe: ExternalAgentProbe) {
  if (!probe.installed) return probe.reason || "command_not_found";
  if (probe.command_source === "PATH") return "已通过 PATH 配置（路径已隐藏）";
  if (probe.command_source?.startsWith("env:")) {
    return "已通过环境变量配置（路径已隐藏）";
  }
  return "已配置（路径已隐藏）";
}

function statusColor(status: string) {
  if (status === "completed") return "green";
  if (status === "running") return "blue";
  if (status === "degraded") return "orange";
  if (status === "cancelled") return "default";
  if (status === "failed") return "red";
  return "default";
}
