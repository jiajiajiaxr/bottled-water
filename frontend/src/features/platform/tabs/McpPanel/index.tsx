import { useState } from "react";
import {
  App as AntApp,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Tag,
} from "antd";
import {
  CloudUploadOutlined,
  DeleteOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { api } from "@/api";
import { parseList } from "@/lib/format";
import type { Conversation, McpInvocation, McpServer, Workspace } from "@/types";

const { TextArea } = Input;

interface McpPanelProps {
  activeWorkspace?: Workspace;
  activeConversation?: Conversation;
}

export function McpPanel({ activeWorkspace, activeConversation }: McpPanelProps) {
  const { message } = AntApp.useApp();
  const [mcpForm] = Form.useForm();
  const [mcpImportForm] = Form.useForm();

  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [mcpInvocations, setMcpInvocations] = useState<McpInvocation[]>([]);
  const [mcpInvocationResult, setMcpInvocationResult] = useState("");

  return (
    <div className="workspace-grid">
      <Card title="注册 MCP 服务">
        <Form
          form={mcpForm}
          layout="vertical"
          initialValues={{
            transport: "stdio",
            command: "agenthub-mcp-sandbox",
            enabled: true,
            timeout_ms: 30000,
            retry: 1,
          }}
          onFinish={async (values) => {
            const server = await api.createMcpServer({
              workspace_id: activeWorkspace?.id,
              ...values,
              args: parseList(values.args),
              tool_filter: parseList(values.tool_filter),
              enabled: Boolean(values.enabled),
            });
            setMcpServers((current) => [server, ...current]);
            mcpForm.resetFields([
              "name",
              "url",
              "args",
              "tool_filter",
            ]);
            message.success("MCP 服务已注册");
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true }]}
          >
            <Input placeholder="文件系统 MCP" />
          </Form.Item>
          <Form.Item name="transport" label="传输">
            <Select
              options={[
                { label: "stdio", value: "stdio" },
                { label: "SSE", value: "sse" },
                { label: "HTTP Stream", value: "httpStream" },
                { label: "WebSocket", value: "ws" },
              ]}
            />
          </Form.Item>
          <Form.Item name="command" label="命令">
            <Input placeholder="npx -y @modelcontextprotocol/server-filesystem" />
          </Form.Item>
          <Form.Item name="url" label="URL">
            <Input placeholder="https://mcp.example.com/sse" />
          </Form.Item>
          <Form.Item name="args" label="参数">
            <Input placeholder="--root, E:/字节跳动/agenthub" />
          </Form.Item>
          <Form.Item name="tool_filter" label="工具白名单">
            <Input placeholder="file.*, browser.*, sandbox.*" />
          </Form.Item>
          <Space>
            <Form.Item name="enabled" valuePropName="checked">
              <Checkbox>启用</Checkbox>
            </Form.Item>
            <Form.Item name="timeout_ms" label="超时">
              <Input type="number" />
            </Form.Item>
          </Space>
          <Button
            type="primary"
            htmlType="submit"
            disabled={!activeWorkspace}
          >
            注册服务
          </Button>
        </Form>
      </Card>
      <Card title="服务与工具">
        <List
          dataSource={mcpServers}
          locale={{ emptyText: "暂无 MCP 服务" }}
          renderItem={(server) => (
            <List.Item
              actions={[
                <Button
                  key="probe"
                  size="small"
                  icon={<ToolOutlined />}
                  onClick={async () => {
                    const updated = await api.probeMcpServer(
                      server.id,
                    );
                    setMcpServers((current) =>
                      current.map((item) =>
                        item.id === server.id ? updated : item,
                      ),
                    );
                  }}
                >
                  探测
                </Button>,
                <Button
                  key="invoke"
                  size="small"
                  disabled={
                    !(
                      server.tools?.[0]?.name ||
                      server.tool_filter?.[0]
                    )
                  }
                  onClick={async () => {
                    const toolName =
                      server.tools?.[0]?.name ||
                      server.tool_filter?.[0];
                    if (!toolName) return;
                    const result = await api.invokeMcpTool(
                      server.id,
                      toolName,
                      { input: "ping" },
                      activeConversation?.id,
                    );
                    setMcpInvocations((current) => [
                      result,
                      ...current,
                    ]);
                    setMcpInvocationResult(
                      JSON.stringify(
                        result.result || result.error_message,
                        null,
                        2,
                      ),
                    );
                  }}
                >
                  Invoke
                </Button>,
                <Button
                  key="delete"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => {
                    Modal.confirm({
                      title: `删除 MCP 服务：${server.name}`,
                      content:
                        "删除后该服务、关联工具调用入口将从当前目录移除。",
                      okText: "删除",
                      okButtonProps: { danger: true },
                      onOk: async () => {
                        await api.deleteMcpServer(server.id);
                        setMcpServers((current) =>
                          current.filter(
                            (item) => item.id !== server.id,
                          ),
                        );
                        message.success("MCP 服务已删除");
                      },
                    });
                  }}
                />,
              ]}
            >
              <List.Item.Meta
                avatar={
                  <Badge
                    color={
                      server.health_status === "online"
                        ? "green"
                        : "orange"
                    }
                  >
                    <Avatar icon={<ToolOutlined />} />
                  </Badge>
                }
                title={
                  <Space>
                    <strong>{server.name}</strong>
                    <Tag>{server.transport}</Tag>
                    <Tag>{server.health_status}</Tag>
                  </Space>
                }
                description={
                  <Space wrap>
                    {(server.tools ?? []).map((tool) => (
                      <Tag
                        key={tool.name}
                        color={
                          tool.enabled === false ? "default" : "blue"
                        }
                      >
                        {tool.name}
                      </Tag>
                    ))}
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>
      <Card title="导入 MCP" data-testid="mcp-import-card">
        <Form
          form={mcpImportForm}
          layout="vertical"
          initialValues={{ source_type: "manifest_url" }}
          onFinish={async (values) => {
            const server = await api.importMcpServer({
              workspace_id: activeWorkspace?.id,
              source_type: values.source_type,
              source: values.source,
            });
            setMcpServers((current) => [server, ...current]);
            mcpImportForm.resetFields(["source"]);
            message.success("MCP 已导入");
          }}
        >
          <Form.Item name="source_type" label="导入类型">
            <Select
              options={[
                { label: "Manifest URL", value: "manifest_url" },
                { label: "JSON 配置", value: "json" },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="source"
            label="URL / JSON"
            rules={[{ required: true }]}
          >
            <TextArea
              rows={5}
              placeholder='https://example.com/mcp.json 或 {"name":"filesystem","transport":"stdio"}'
            />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            icon={<CloudUploadOutlined />}
            disabled={!activeWorkspace}
          >
            导入 MCP
          </Button>
        </Form>
      </Card>
    </div>
  );
}
