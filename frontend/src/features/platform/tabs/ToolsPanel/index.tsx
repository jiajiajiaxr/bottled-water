import { useEffect, useState } from "react";
import {
  App as AntApp,
  Avatar,
  Button,
  Card,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Tag,
} from "antd";
import {
  DeleteOutlined,
  RobotOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { api } from "@/api";
import { parseList } from "@/lib/format";
import type { Conversation, ToolDefinition, Workspace } from "@/types";

const { TextArea } = Input;

interface ToolsPanelProps {
  activeWorkspace?: Workspace;
  activeConversation?: Conversation;
}

export function ToolsPanel({ activeWorkspace, activeConversation }: ToolsPanelProps) {
  const { message } = AntApp.useApp();
  const [toolForm] = Form.useForm();
  const [toolGenerateForm] = Form.useForm();

  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [toolInvokeResult, setToolInvokeResult] = useState("");

  const load = async () => {
    try {
      const items = await api.tools(activeWorkspace?.id).catch(() => [] as ToolDefinition[]);
      setTools(items);
    } catch {
      message.error("加载工具目录失败");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace?.id]);

  return (
    <div className="workspace-grid">
      <Card title="自定义工具">
        <Form
          form={toolForm}
          layout="vertical"
          initialValues={{
            category: "custom",
            type: "custom_python",
            permissions: "tool:invoke",
            code: "text = str(arguments.get('input') or '')\nresult = {'echo': text, 'length': len(text)}",
          }}
          onFinish={async (values) => {
            const tool = await api.createTool({
              workspace_id: activeWorkspace?.id,
              name: values.name,
              display_name: values.display_name,
              description: values.description ?? "",
              category: values.category,
              type: values.type,
              permissions: parseList(values.permissions),
              implementation: {
                language: "python",
                code: values.code,
              },
              runtime: {
                mode: "restricted_python",
                workspace: "var/ai-tools",
              },
              tags: parseList(values.tags),
            });
            setTools((current) => [tool, ...current]);
            toolForm.resetFields([
              "name",
              "display_name",
              "description",
            ]);
            message.success("工具已创建");
          }}
        >
          <Space align="start">
            <Form.Item
              name="name"
              label="工具名"
              rules={[{ required: true }]}
            >
              <Input placeholder="custom_release_notes" />
            </Form.Item>
            <Form.Item name="display_name" label="显示名">
              <Input placeholder="发布说明生成器" />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="描述">
            <Input placeholder="说明这个工具适合什么任务" />
          </Form.Item>
          <Space align="start">
            <Form.Item name="category" label="分类">
              <Input style={{ width: 150 }} />
            </Form.Item>
            <Form.Item name="type" label="运行时">
              <Select
                style={{ width: 170 }}
                options={[
                  { label: "受限 Python", value: "custom_python" },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="permissions" label="权限">
            <Input placeholder="逗号分隔，如 file:read,artifact:create" />
          </Form.Item>
          <Form.Item name="code" label="工具代码">
            <TextArea rows={5} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Input placeholder="逗号分隔" />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            disabled={!activeWorkspace}
          >
            保存工具
          </Button>
        </Form>
      </Card>
      <Card title="AI 构建工具">
        <Form
          form={toolGenerateForm}
          layout="vertical"
          initialValues={{
            category: "custom",
            allowed_permissions: "tool:invoke",
          }}
          onFinish={async (values) => {
            const tool = await api.generateTool({
              workspace_id: activeWorkspace?.id,
              name: values.name,
              intent: values.intent,
              requirements: values.requirements,
              category: values.category,
              allowed_permissions: parseList(
                values.allowed_permissions,
              ),
              tags: parseList(values.tags),
            });
            setTools((current) => [tool, ...current]);
            toolGenerateForm.resetFields([
              "name",
              "intent",
              "requirements",
            ]);
            message.success("AI 已构建工具并写入后端工具工作区");
          }}
        >
          <Form.Item name="name" label="工具名">
            <Input placeholder="留空由 AI 命名" />
          </Form.Item>
          <Form.Item
            name="intent"
            label="工具目标"
            rules={[{ required: true }]}
          >
            <TextArea
              rows={3}
              placeholder="例如：把输入的需求整理成验收清单 JSON"
            />
          </Form.Item>
          <Form.Item name="requirements" label="实现约束">
            <TextArea
              rows={3}
              placeholder="输入输出格式、权限边界、异常处理要求"
            />
          </Form.Item>
          <Space align="start">
            <Form.Item name="category" label="分类">
              <Input style={{ width: 150 }} />
            </Form.Item>
            <Form.Item name="allowed_permissions" label="授权权限">
              <Input style={{ width: 220 }} />
            </Form.Item>
          </Space>
          <Form.Item name="tags" label="标签">
            <Input placeholder="ai-generated,workflow" />
          </Form.Item>
          <Button
            icon={<RobotOutlined />}
            type="primary"
            htmlType="submit"
            disabled={!activeWorkspace}
          >
            AI 创建工具
          </Button>
        </Form>
      </Card>
      <Card title="工具目录">
        {toolInvokeResult && (
          <div className="result-box">{toolInvokeResult}</div>
        )}
        <List
          dataSource={tools}
          locale={{ emptyText: "暂无工具" }}
          renderItem={(tool) => (
            <List.Item
              actions={[
                <Button
                  key="invoke"
                  size="small"
                  onClick={async () => {
                    if (
                      tool.name.startsWith("artifact.create") &&
                      !activeConversation?.id
                    ) {
                      message.warning("先选择一个会话再测试产物工具");
                      return;
                    }
                    const args =
                      tool.name === "db.inspect"
                        ? {}
                        : tool.name.startsWith("artifact.create")
                          ? {
                              conversation_id: activeConversation?.id,
                              title: "工具调用产物",
                              body: "这是由 AgentHub 工具层生成的产物。",
                            }
                          : { input: "ping" };
                    const result = await api.invokeTool(
                      tool.name,
                      args,
                      activeWorkspace?.id,
                    );
                    setToolInvokeResult(
                      JSON.stringify(result.result, null, 2),
                    );
                  }}
                >
                  测试
                </Button>,
                !tool.is_builtin && (
                  <Button
                    key="delete"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      Modal.confirm({
                        title: `删除工具：${tool.display_name ?? tool.name}`,
                        content:
                          "删除后该工具不会再出现在工具目录，也不能被 Agent 授权使用。",
                        okText: "删除",
                        okButtonProps: { danger: true },
                        onOk: async () => {
                          await api.deleteTool(tool.id);
                          setTools((current) =>
                            current.filter(
                              (item) => item.id !== tool.id,
                            ),
                          );
                          message.success("工具已删除");
                        },
                      });
                    }}
                  />
                ),
              ]}
            >
              <List.Item.Meta
                avatar={<Avatar icon={<ToolOutlined />} />}
                title={
                  <Space wrap>
                    <strong>
                      {tool.display_name ?? tool.name}
                    </strong>
                    <Tag>{tool.category}</Tag>
                    <Tag color={tool.is_builtin ? "blue" : "purple"}>
                      {tool.is_builtin ? "内置" : "自定义"}
                    </Tag>
                    <Tag>{tool.status}</Tag>
                  </Space>
                }
                description={
                  <Space direction="vertical" size={4}>
                    <span className="ant-typography ant-typography-secondary">
                      {tool.name} · {tool.description}
                    </span>
                    <Space size={[4, 4]} wrap>
                      {tool.permissions
                        .slice(0, 6)
                        .map((permission) => (
                          <Tag key={permission}>{permission}</Tag>
                        ))}
                    </Space>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
