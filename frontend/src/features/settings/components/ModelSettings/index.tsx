/**
 * 模型设置面板
 *
 * 以模型配置为核心组织界面：
 * - 厂商为预制只读信息（URL、类型等）
 * - 模型配置为用户可写（API Key、参数等），随时可编辑
 * - 列表视图：卡片式展示用户创建的模型配置
 * - 编辑视图：点击卡片进入可编辑表单
 * - 创建流程：选择厂商后直接生成默认卡片，随即进入编辑
 */

import { useEffect, useState } from "react";
import {
  ArrowLeftOutlined,
  PlusOutlined,
  ApiOutlined,
  EyeOutlined,
  PlayCircleOutlined,
  DeleteOutlined,
  SaveOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  Dropdown,
  Divider,
  Avatar,
} from "antd";
import type { MenuProps } from "antd";
import { api } from "@/api";
import type { ModelConfig, ModelProvider, BuiltinProvider, User } from "@/types";

const { Text } = Typography;

type View = "list" | "edit";

const PURPOSE_OPTIONS = [
  { label: "聊天", value: "chat" },
  { label: "主控", value: "master" },
  { label: "Worker", value: "worker" },
  { label: "Reviewer", value: "reviewer" },
  { label: "摘要", value: "summary" },
];

interface ModelSettingsProps {
  /** 父组件传入的 message 实例，用于显示全局提示 */
  message: {
    success: (content: string) => void;
    error: (content: string) => void;
  };
  user: User;
  onUserUpdated: (user: User) => void;
}

export function ModelSettings({ message, user, onUserUpdated }: ModelSettingsProps) {
  // === 数据 ===
  const [modelProviders, setModelProviders] = useState<ModelProvider[]>([]);
  const [builtinProviders, setBuiltinProviders] = useState<BuiltinProvider[]>([]);
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(false);

  // === 视图状态 ===
  const [view, setView] = useState<View>("list");
  const [editingConfig, setEditingConfig] = useState<ModelConfig | null>(null);

  // === 厂商信息 Modal（只读） ===
  const [providerModalOpen, setProviderModalOpen] = useState(false);

  // === 表单 ===
  const [configForm] = Form.useForm();

  // === 测试 ===
  const [testResult, setTestResult] = useState("");
  const [testing, setTesting] = useState(false);

  /** 加载模型配置和厂商数据 */
  const loadModels = async () => {
    setLoading(true);
    try {
      const [providers, configs, builtins] = await Promise.all([
        api.modelProviders(),
        api.modelConfigs(),
        api.builtinProviders(),
      ]);
      setModelProviders(providers);
      setModelConfigs(configs);
      setBuiltinProviders(builtins);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadModels();
  }, []);

  // -----------------------------------------------------------
  // 模型配置操作
  // -----------------------------------------------------------

  /** 用厂商默认信息快速创建模型配置，然后进入编辑 */
  const handleQuickCreate = async (providerType: string) => {
    const provider = builtinProviders.find((p) => p.provider_type === providerType);
    if (!provider) return;
    setLoading(true);
    try {
      const created = await api.createModelConfig({
        provider_type: providerType,
        name: provider.default_model || provider.name,
        model_id: provider.default_model || "",
        purpose: "chat",
        context_window: 128000,
        max_output_tokens: 4096,
        temperature_default: 0.4,
      });
      message.success("模型配置已创建");
      await loadModels();
      openEditor(created);
    } finally {
      setLoading(false);
    }
  };

  /** 保存编辑后的模型配置 */
  const handleSaveEdit = async (values: Record<string, unknown>) => {
    if (!editingConfig) return;
    const config: Record<string, unknown> = {};
    if (values.api_key) {
      config.api_key = String(values.api_key);
    }
    await api.updateModelConfig(editingConfig.id, {
      name: String(values.name),
      model_id: String(values.model_id),
      purpose: String(values.purpose),
      context_window: Number(values.context_window) || 128000,
      max_output_tokens: Number(values.max_output_tokens) || 4096,
      temperature_default: Number(values.temperature_default) || 0.4,
      config,
    });
    message.success("模型配置已更新");
    await loadModels();
  };

  /** 测试模型连通性 */
  const handleTest = async (prompt: string, configId?: string) => {
    setTesting(true);
    setTestResult("正在等待模型回复...");
    try {
      const result = await api.testModel(
        prompt || "请回复模型已就绪。",
        configId,
      );
      setTestResult(`${result.model}: ${result.response}`);
    } catch (err) {
      setTestResult(
        `连接失败：${err instanceof Error ? err.message : "unknown"}`,
      );
    } finally {
      setTesting(false);
    }
  };

  /** 删除模型配置 */
  const handleDeleteConfig = (config: ModelConfig) => {
    Modal.confirm({
      title: "删除模型配置",
      content: `确定删除模型配置 "${config.name}" 吗？此操作不可恢复。`,
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        await api.deleteModelConfig(config.id);
        message.success("模型配置已删除");
        setView("list");
        await loadModels();
      },
    });
  };

  /** 启动模型配置（设为默认） */
  const handleActivate = async (config: ModelConfig, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const result = await api.activateModelConfig(config.id);
      message.success(`已启用模型：${result.name}`);
      onUserUpdated({ ...user, default_model_config_id: config.id });
    } catch (err) {
      message.error(err instanceof Error ? err.message : "启用失败");
    }
  };

  /** 打开编辑器并初始化表单 */
  const openEditor = (config: ModelConfig) => {
    setEditingConfig(config);
    setTestResult("");
    const apiKey =
      config.config &&
      typeof config.config === "object" &&
      "api_key" in config.config
        ? String(config.config.api_key)
        : "";
    configForm.setFieldsValue({
      name: config.name,
      model_id: config.model_id,
      api_key: apiKey,
      purpose: config.purpose,
      context_window: config.context_window,
      max_output_tokens: config.max_output_tokens,
      temperature_default: config.temperature_default,
    });
    setView("edit");
  };

  // -----------------------------------------------------------
  // 新增模型下拉
  // -----------------------------------------------------------

  const addModelMenuItems: MenuProps["items"] = builtinProviders.map((p) => ({
    key: p.provider_type,
    label: p.name,
    icon: <ApiOutlined />,
  }));

  // -----------------------------------------------------------
  // 渲染：列表视图
  // -----------------------------------------------------------

  if (view === "list") {
    return (
      <div>
        <Space style={{ marginBottom: 16 }}>
          <Dropdown
            menu={{
              items: addModelMenuItems,
              onClick: ({ key }) => handleQuickCreate(String(key)),
            }}
            disabled={!builtinProviders.length || loading}
          >
            <Button type="primary" icon={<PlusOutlined />} loading={loading}>
              新增模型
            </Button>
          </Dropdown>
          <Button
            icon={<EyeOutlined />}
            onClick={() => setProviderModalOpen(true)}
          >
            查看厂商
          </Button>
        </Space>

        {loading && modelConfigs.length === 0 ? (
          <Spin tip="加载中..." />
        ) : modelConfigs.length === 0 ? (
          <Empty description="暂无模型配置">
            {builtinProviders.length > 0 && (
              <Dropdown
                menu={{
                  items: addModelMenuItems,
                  onClick: ({ key }) => handleQuickCreate(String(key)),
                }}
              >
                <Button type="primary" icon={<PlusOutlined />}>
                  新增模型
                </Button>
              </Dropdown>
            )}
          </Empty>
        ) : (
          <List
            grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 2, xl: 3 }}
            dataSource={modelConfigs}
            renderItem={(config) => {
              const provider = modelProviders.find(
                (p) => p.id === config.provider_id,
              );
              const isActive = user.default_model_config_id === config.id;
              return (
                <List.Item>
                  <Card
                    hoverable
                    onClick={() => openEditor(config)}
                    actions={[
                      isActive ? (
                        <Tag color="blue" key="active">运行中</Tag>
                      ) : (
                        <Button
                          type="link"
                          key="activate"
                          icon={<RocketOutlined />}
                          onClick={(e) => handleActivate(config, e)}
                        >
                          启动
                        </Button>
                      ),
                    ]}
                  >
                    <Card.Meta
                      avatar={<Avatar icon={<ApiOutlined />} />}
                      title={
                        <Space>
                          <Text strong>{config.name}</Text>
                          <Tag>{config.purpose}</Tag>
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size={0}>
                          <Text type="secondary">
                            {provider?.name ?? config.provider_id}
                          </Text>
                          <Text type="secondary" code>
                            {config.model_id}
                          </Text>
                          <Tag
                            color={
                              config.status === "active" ? "green" : "red"
                            }
                          >
                            {config.status}
                          </Tag>
                        </Space>
                      }
                    />
                  </Card>
                </List.Item>
              );
            }}
          />
        )}

        {/* 厂商信息 Modal（只读） */}
        <Modal
          title="厂商信息"
          open={providerModalOpen}
          onCancel={() => setProviderModalOpen(false)}
          footer={
            <Button onClick={() => setProviderModalOpen(false)}>关闭</Button>
          }
          width={640}
        >
          <List
            size="small"
            dataSource={builtinProviders}
            renderItem={(provider) => (
              <List.Item>
                <List.Item.Meta
                  avatar={<Avatar icon={<ApiOutlined />} />}
                  title={
                    <Space>
                      <Text strong>{provider.name}</Text>
                      <Tag>{provider.provider_type}</Tag>
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={0}>
                      <Text type="secondary">{provider.base_url || "-"}</Text>
                      <Text type="secondary">
                        默认模型：{provider.default_model || "-"}
                      </Text>
                      <Space>
                        {provider.supports_streaming && (
                          <Tag>支持流式</Tag>
                        )}
                        {provider.supports_embeddings && (
                          <Tag>支持 Embedding</Tag>
                        )}
                      </Space>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        </Modal>
      </div>
    );
  }

  // -----------------------------------------------------------
  // 渲染：编辑视图
  // -----------------------------------------------------------

  if (view === "edit" && editingConfig) {
    const provider = modelProviders.find(
      (p) => p.id === editingConfig.provider_id,
    );
    return (
      <div>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={() => setView("list")}
          style={{ marginBottom: 16 }}
        >
          返回列表
        </Button>
        <Card
          title={
            <Space>
              <ApiOutlined />
              <Text strong>{editingConfig.name}</Text>
            </Space>
          }
          extra={
            <Button
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDeleteConfig(editingConfig)}
            >
              删除
            </Button>
          }
        >
          <Form
            form={configForm}
            layout="vertical"
            onFinish={handleSaveEdit}
          >
            <Form.Item label="厂商">
              <Input value={provider?.name} disabled />
            </Form.Item>
            <Space align="start">
              <Form.Item
                name="name"
                label="名称"
                rules={[{ required: true }]}
              >
                <Input placeholder="Master/Reviewer 模型" />
              </Form.Item>
              <Form.Item
                name="model_id"
                label="模型 ID"
                rules={[{ required: true }]}
              >
                <Input placeholder="doubao-seed-2-0-lite" />
              </Form.Item>
            </Space>
            <Form.Item name="api_key" label="API Key">
              <Input.Password placeholder="在此输入该模型的 API Key" />
            </Form.Item>
            <Space align="start">
              <Form.Item name="purpose" label="用途">
                <Select style={{ width: 150 }} options={PURPOSE_OPTIONS} />
              </Form.Item>
              <Form.Item name="context_window" label="上下文窗口">
                <Input type="number" />
              </Form.Item>
              <Form.Item name="max_output_tokens" label="最大输出">
                <Input type="number" />
              </Form.Item>
              <Form.Item name="temperature_default" label="温度">
                <Input type="number" step="0.1" />
              </Form.Item>
            </Space>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>
                保存
              </Button>
            </Space>
          </Form>

          <Divider />

          <Input.Search
            placeholder="输入测试提示词"
            enterButton={
              <Space>
                <PlayCircleOutlined />
                {testing ? "等待中" : "测试"}
              </Space>
            }
            loading={testing}
            onSearch={(prompt) => handleTest(prompt, editingConfig.id)}
          />
          {testResult && (
            <div className="result-box">{testResult}</div>
          )}
        </Card>
      </div>
    );
  }

  return null;
}
