import { useEffect, useState } from "react";
import { ApiOutlined, DeleteOutlined, EditOutlined } from "@ant-design/icons";
import {
  App as AntApp,
  Avatar,
  Button,
  Card,
  Checkbox,
  Divider,
  Drawer,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { api } from "@/api";
import type { ModelConfig, ModelProvider, User } from "@/types";

const { Text } = Typography;

export function GlobalSettingsDrawer({
  open,
  user,
  onClose,
  onUserUpdated,
}: {
  open: boolean;
  user: User;
  onClose: () => void;
  onUserUpdated: (user: User) => void;
}) {
  const [profileForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [providerForm] = Form.useForm();
  const [modelForm] = Form.useForm();
  const [modelProviders, setModelProviders] = useState<ModelProvider[]>([]);
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [modelTestResult, setModelTestResult] = useState("");
  const [modelTesting, setModelTesting] = useState(false);
  const [editingProviderId, setEditingProviderId] = useState<string | null>(null);
  const { message } = AntApp.useApp();

  const loadModels = async () => {
    const [providers, configs] = await Promise.all([
      api.modelProviders(),
      api.modelConfigs(),
    ]);
    setModelProviders(providers);
    setModelConfigs(configs);
  };

  useEffect(() => {
    if (!open) return;
    profileForm.setFieldsValue({ display_name: user.name });
    loadModels().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user.id]);

  return (
    <Drawer title="全局设置" width={920} open={open} onClose={onClose}>
      <Tabs
        items={[
          {
            key: "account",
            label: "账号",
            children: (
              <div className="workspace-grid">
                <Card title="个人资料">
                  <Form
                    form={profileForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      const updated = await api.updateProfile({
                        display_name: values.display_name,
                      });
                      onUserUpdated(updated);
                      message.success("个人资料已更新");
                    }}
                  >
                    <Form.Item
                      name="display_name"
                      label="显示名称"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Button type="primary" htmlType="submit">
                      保存资料
                    </Button>
                  </Form>
                </Card>
                <Card title="修改密码">
                  <Form
                    form={passwordForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      await api.changePassword({
                        current_password: values.current_password,
                        new_password: values.new_password,
                      });
                      passwordForm.resetFields();
                      message.success("密码已更新");
                    }}
                  >
                    <Form.Item
                      name="current_password"
                      label="当前密码"
                      rules={[{ required: true }]}
                    >
                      <Input.Password />
                    </Form.Item>
                    <Form.Item
                      name="new_password"
                      label="新密码"
                      rules={[{ required: true, min: 6 }]}
                    >
                      <Input.Password />
                    </Form.Item>
                    <Button htmlType="submit">更新密码</Button>
                  </Form>
                </Card>
              </div>
            ),
          },
          {
            key: "models",
            label: "模型 API",
            children: (
              <div className="workspace-grid">
                <Card title="OpenAI 兼容供应商">
                  <Form
                    form={providerForm}
                    layout="vertical"
                    initialValues={{
                      provider_type: "openai-compatible",
                      base_url: "https://ark.cn-beijing.volces.com/api/v3",
                      default_model: "doubao-seed-2-0-lite",
                      supports_streaming: true,
                    }}
                    onFinish={async (values) => {
                      const payload = {
                        ...values,
                        supports_streaming: Boolean(values.supports_streaming),
                        supports_embeddings: Boolean(
                          values.supports_embeddings,
                        ),
                      };
                      if (editingProviderId) {
                        await api.updateModelProvider(editingProviderId, payload);
                        setEditingProviderId(null);
                        providerForm.resetFields();
                        providerForm.setFieldsValue({
                          provider_type: "openai-compatible",
                          base_url: "https://ark.cn-beijing.volces.com/api/v3",
                          default_model: "doubao-seed-2-0-lite",
                          supports_streaming: true,
                        });
                        await loadModels();
                        message.success("模型供应商已更新");
                      } else {
                        const provider = await api.createModelProvider(payload);
                        setModelProviders((current) => [provider, ...current]);
                        providerForm.resetFields(["name", "api_key"]);
                        await loadModels();
                        message.success("模型供应商已保存");
                      }
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="我的豆包 / OpenAI 兼容模型" />
                    </Form.Item>
                    <Form.Item name="provider_type" label="类型">
                      <Select
                        options={[
                          {
                            label: "OpenAI Compatible",
                            value: "openai-compatible",
                          },
                          { label: "Volcengine Ark", value: "ark" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="base_url"
                      label="Base URL"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item name="api_key" label="API Key">
                      <Input.Password placeholder={editingProviderId ? "留空则保持原密钥" : "只提交到后端，不在前端回显"} />
                    </Form.Item>
                    <Form.Item
                      name="default_model"
                      label="默认模型"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Space>
                      <Form.Item
                        name="supports_streaming"
                        valuePropName="checked"
                      >
                        <Checkbox>流式</Checkbox>
                      </Form.Item>
                      <Form.Item
                        name="supports_embeddings"
                        valuePropName="checked"
                      >
                        <Checkbox>Embedding</Checkbox>
                      </Form.Item>
                    </Space>
                    <Space>
                      <Button type="primary" htmlType="submit">
                        {editingProviderId ? "更新供应商" : "保存供应商"}
                      </Button>
                      {editingProviderId && (
                        <Button
                          onClick={() => {
                            setEditingProviderId(null);
                            providerForm.resetFields();
                            providerForm.setFieldsValue({
                              provider_type: "openai-compatible",
                              base_url: "https://ark.cn-beijing.volces.com/api/v3",
                              default_model: "doubao-seed-2-0-lite",
                              supports_streaming: true,
                            });
                          }}
                        >
                          取消
                        </Button>
                      )}
                    </Space>
                  </Form>
                  <Divider />
                  <List
                    size="small"
                    dataSource={modelProviders}
                    renderItem={(provider) => (
                      <List.Item
                        actions={[
                          <Button
                            key="edit"
                            type="text"
                            icon={<EditOutlined />}
                            onClick={() => {
                              setEditingProviderId(provider.id);
                              providerForm.setFieldsValue({
                                name: provider.name,
                                provider_type: provider.provider_type,
                                base_url: provider.base_url,
                                default_model: provider.default_model,
                                supports_streaming: provider.supports_streaming,
                                supports_embeddings: provider.supports_embeddings,
                              });
                            }}
                          >
                            编辑
                          </Button>,
                          <Button
                            key="delete"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => {
                              Modal.confirm({
                                title: "删除供应商",
                                content: `确定删除供应商 "${provider.name}" 吗？关联的模型配置也会被清理。`,
                                okText: "删除",
                                okType: "danger",
                                cancelText: "取消",
                                onOk: async () => {
                                  await api.deleteModelProvider(provider.id);
                                  await loadModels();
                                  if (editingProviderId === provider.id) {
                                    setEditingProviderId(null);
                                    providerForm.resetFields();
                                    providerForm.setFieldsValue({
                                      provider_type: "openai-compatible",
                                      base_url: "https://ark.cn-beijing.volces.com/api/v3",
                                      default_model: "doubao-seed-2-0-lite",
                                      supports_streaming: true,
                                    });
                                  }
                                  message.success("供应商已删除");
                                },
                              });
                            }}
                          >
                            删除
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<Avatar icon={<ApiOutlined />} />}
                          title={
                            <Space>
                              <Text strong>{provider.name}</Text>
                              <Tag>{provider.provider_type}</Tag>
                              <Tag color={provider.status === "active" ? "green" : "red"}>{provider.status}</Tag>
                            </Space>
                          }
                          description={`${provider.base_url} / 默认: ${provider.default_model}`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
                <Card title="模型配置与真实测试">
                  <Form
                    form={modelForm}
                    layout="vertical"
                    initialValues={{
                      purpose: "chat",
                      context_window: 128000,
                      max_output_tokens: 4096,
                      temperature_default: 0.4,
                    }}
                    onFinish={async (values) => {
                      const model = await api.createModelConfig(values);
                      setModelConfigs((current) => [model, ...current]);
                      modelForm.resetFields(["name", "model_id"]);
                      message.success("模型配置已创建");
                    }}
                  >
                    <Form.Item
                      name="provider_id"
                      label="供应商"
                      rules={[{ required: true }]}
                    >
                      <Select
                        options={modelProviders.map((provider) => ({
                          label: provider.name,
                          value: provider.id,
                        }))}
                      />
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
                    <Space align="start">
                      <Form.Item name="purpose" label="用途">
                        <Select
                          style={{ width: 150 }}
                          options={[
                            { label: "聊天", value: "chat" },
                            { label: "主控", value: "master" },
                            { label: "Worker", value: "worker" },
                            { label: "Reviewer", value: "reviewer" },
                            { label: "摘要", value: "summary" },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item name="temperature_default" label="温度">
                        <Input type="number" step="0.1" />
                      </Form.Item>
                    </Space>
                    <Button htmlType="submit" disabled={!modelProviders.length}>
                      新增模型
                    </Button>
                  </Form>
                  <Divider />
                  <Input.Search
                    placeholder="输入测试提示词"
                    enterButton={modelTesting ? "等待中" : "测试"}
                    loading={modelTesting}
                    onSearch={async (prompt) => {
                      const currentModel = modelConfigs[0];
                      setModelTesting(true);
                      setModelTestResult("正在等待模型回复...");
                      try {
                        const result = await api.testModel(
                          prompt || "请回复模型已就绪。",
                          currentModel?.id,
                        );
                        setModelTestResult(
                          `${result.model}: ${result.response}`,
                        );
                      } catch (error) {
                        setModelTestResult(
                          `连接失败：${error instanceof Error ? error.message : "unknown"}`,
                        );
                      } finally {
                        setModelTesting(false);
                      }
                    }}
                  />
                  {modelTestResult && (
                    <div className="result-box">{modelTestResult}</div>
                  )}
                  <List
                    size="small"
                    dataSource={modelConfigs}
                    renderItem={(model) => (
                      <List.Item>
                        <List.Item.Meta
                          avatar={<Avatar icon={<ApiOutlined />} />}
                          title={
                            <Space>
                              <Text strong>{model.name}</Text>
                              <Tag>{model.purpose}</Tag>
                              <Tag>{model.status}</Tag>
                            </Space>
                          }
                          description={`${model.provider_name ?? model.provider_id} / ${model.model_id} / ${model.context_window} tokens`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
          {
            key: "general",
            label: "常规",
            children: (
              <Card>
                <Space direction="vertical">
                  <Checkbox defaultChecked>发送消息后自动滚动到底部</Checkbox>
                  <Checkbox defaultChecked>流式回复时显示运行状态</Checkbox>
                  <Checkbox defaultChecked>
                    产物卡片点击后再打开右侧预览
                  </Checkbox>
                </Space>
              </Card>
            ),
          },
        ]}
      />
    </Drawer>
  );
}
