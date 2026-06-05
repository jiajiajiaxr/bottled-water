import { useEffect, useState } from "react";
import {
  App as AntApp,
  Avatar,
  Badge,
  Button,
  Card,
  Divider,
  Form,
  Input,
  List,
  Select,
  Space,
  Tag,
} from "antd";
import { CloudUploadOutlined } from "@ant-design/icons";
import { api } from "@/api";
import { parseList } from "@/lib/format";
import type {
  RemoteConnection,
  SandboxCommandResult,
  SandboxSession,
  Workspace,
} from "@/types";

interface SandboxPanelProps {
  activeWorkspace?: Workspace;
}

export function SandboxPanel({ activeWorkspace }: SandboxPanelProps) {
  const { message } = AntApp.useApp();
  const [sandboxForm] = Form.useForm();
  const [commandForm] = Form.useForm();
  const [remoteForm] = Form.useForm();

  const [sandboxes, setSandboxes] = useState<SandboxSession[]>([]);
  const [selectedSandbox, setSelectedSandbox] = useState<string>();
  const [remoteConnections, setRemoteConnections] = useState<
    RemoteConnection[]
  >([]);
  const [sandboxResult, setSandboxResult] = useState<SandboxCommandResult>();

  const load = async () => {
    try {
      const [items, remotes] = await Promise.all([
        api.sandboxes().catch(() => [] as SandboxSession[]),
        api.remoteConnections().catch(() => [] as RemoteConnection[]),
      ]);
      setSandboxes(items);
      setRemoteConnections(remotes);
    } catch {
      message.error("加载沙箱与远程连接数据失败");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="workspace-grid">
      <Card title="沙箱控制">
        <Form
          form={sandboxForm}
          layout="vertical"
          initialValues={{ image: "python:3.11-node20" }}
          onFinish={async (values) => {
            const sandbox = await api.createSandbox({
              workspace_id: activeWorkspace?.id,
              ...values,
            });
            setSandboxes((current) => [sandbox, ...current]);
            setSelectedSandbox(sandbox.id);
            sandboxForm.resetFields(["name"]);
            message.success("沙箱已创建");
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true }]}
          >
            <Input placeholder="前端构建沙箱" />
          </Form.Item>
          <Form.Item name="image" label="镜像">
            <Input />
          </Form.Item>
          <Button htmlType="submit" disabled={!activeWorkspace}>
            创建沙箱
          </Button>
        </Form>
        <Divider />
        <Select
          className="full-width"
          placeholder="选择沙箱"
          value={selectedSandbox}
          onChange={setSelectedSandbox}
          options={sandboxes.map((sandbox) => ({
            label: `${sandbox.name} · ${sandbox.status}`,
            value: sandbox.id,
          }))}
        />
        <Form
          className="mt-8"
          form={commandForm}
          layout="vertical"
          initialValues={{
            command: "pytest -q",
            timeout_seconds: 120,
          }}
          onFinish={async (values) => {
            if (!selectedSandbox) return;
            const result = await api.runSandboxCommand(
              selectedSandbox,
              values,
            );
            setSandboxResult(result.result);
            setSandboxes((current) =>
              current.map((item) =>
                item.id === selectedSandbox ? result.sandbox : item,
              ),
            );
          }}
        >
          <Form.Item
            name="command"
            label="命令"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="timeout_seconds" label="超时秒数">
            <Input type="number" />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            disabled={!selectedSandbox}
          >
            执行
          </Button>
        </Form>
        {sandboxResult && (
          <div className="terminal-box">
            <span>{sandboxResult.command}</span>
            <pre>{sandboxResult.stdout || sandboxResult.stderr}</pre>
          </div>
        )}
      </Card>
      <Card title="远程连接">
        <Form
          form={remoteForm}
          layout="vertical"
          initialValues={{
            connection_type: "browser",
            endpoint: "http://127.0.0.1:5173",
            capabilities: "open,screenshot,inspect",
          }}
          onFinish={async (values) => {
            const remote = await api.createRemoteConnection({
              workspace_id: activeWorkspace?.id,
              ...values,
              capabilities: parseList(values.capabilities),
            });
            setRemoteConnections((current) => [remote, ...current]);
            remoteForm.resetFields(["name"]);
            message.success("远程连接已创建");
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true }]}
          >
            <Input placeholder="预览浏览器" />
          </Form.Item>
          <Form.Item name="connection_type" label="类型">
            <Select
              options={[
                { label: "Browser", value: "browser" },
                { label: "SSH", value: "ssh" },
                { label: "VNC", value: "vnc" },
                { label: "RDP", value: "rdp" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="endpoint"
            label="Endpoint"
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="capabilities" label="能力">
            <Input />
          </Form.Item>
          <Button htmlType="submit" disabled={!activeWorkspace}>
            新建连接
          </Button>
        </Form>
        <Divider />
        <List
          dataSource={remoteConnections}
          locale={{ emptyText: "暂无远程连接" }}
          renderItem={(remote) => (
            <List.Item
              actions={[
                <Button
                  key="connect"
                  size="small"
                  icon={<CloudUploadOutlined />}
                  onClick={async () => {
                    const updated = await api.connectRemote(remote.id);
                    setRemoteConnections((current) =>
                      current.map((item) =>
                        item.id === remote.id ? updated : item,
                      ),
                    );
                  }}
                >
                  连接
                </Button>,
              ]}
            >
              <List.Item.Meta
                avatar={
                  <Badge
                    status={
                      remote.status === "connected"
                        ? "success"
                        : "default"
                    }
                  >
                    <Avatar icon={<CloudUploadOutlined />} />
                  </Badge>
                }
                title={
                  <Space>
                    <strong>{remote.name}</strong>
                    <Tag>{remote.connection_type}</Tag>
                    <Tag>{remote.status}</Tag>
                  </Space>
                }
                description={`${remote.endpoint} · ${remote.capabilities.join("/")}`}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
