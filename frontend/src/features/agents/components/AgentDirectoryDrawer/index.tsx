import { useEffect, useState } from "react";
import {
  DeleteOutlined,
  EditOutlined,
  RobotOutlined,
  SearchOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Drawer,
  Flex,
  Form,
  Input,
  List,
  Modal,
  Select,
  Space,
  Steps,
  Tag,
  Typography,
} from "antd";
import { api } from "@/api";
import type {
  Agent,
  AgentCapability,
  McpServer,
  ModelConfig,
  Skill,
  ToolDefinition,
} from "@/types";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

export function AgentDirectoryDrawer({
  open,
  agents,
  onClose,
  onRefresh,
  onCreateAgent,
  onUpdateAgent,
  onDeleteAgent,
  onTestAgent,
}: {
  open: boolean;
  agents: Agent[];
  onClose: () => void;
  onRefresh: () => void;
  onCreateAgent: (agent: Agent) => void;
  onUpdateAgent: (agent: Agent) => void;
  onDeleteAgent: (agent: Agent) => Promise<void>;
  onTestAgent: (agentId: string, text: string) => Promise<string>;
}) {
  const [query, setQuery] = useState("");
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [capabilityText, setCapabilityText] = useState("");
  const [capabilities, setCapabilities] = useState<AgentCapability[]>([]);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [testAgent, setTestAgent] = useState<Agent>();
  const [editingAgent, setEditingAgent] = useState<Agent>();
  const [testText, setTestText] = useState("请用三点说明你的能力。");
  const [testResult, setTestResult] = useState("");
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState("");
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [toolCatalog, setToolCatalog] = useState<ToolDefinition[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const { message } = AntApp.useApp();

  useEffect(() => {
    if (!open) return;
    Promise.all([
      api.modelConfigs().catch(() => []),
      api.tools().catch(() => []),
      api.skills().catch(() => []),
      api.mcpServers().catch(() => []),
    ]).then(([configs, tools, nextSkills, servers]) => {
      setModelConfigs(configs);
      setToolCatalog(tools);
      setSkills(nextSkills);
      setMcpServers(servers);
    });
  }, [open]);

  const toolOptions = toolCatalog.map((tool) => ({
    label: `${tool.display_name ?? tool.name} · ${tool.name}`,
    value: tool.name,
  }));
  const skillOptions = skills.map((skill) => ({
    label: `${skill.name} · ${skill.category}`,
    value: skill.id,
  }));
  const mcpOptions = mcpServers.map((server) => ({
    label: `${server.name} · ${server.transport}`,
    value: server.id,
  }));
  const modelConfigOptions = modelConfigs.map((model) => ({
    label: `${model.name} · ${model.model_id}`,
    value: model.id,
  }));
  const modelLabel = (modelConfigId?: string) => {
    const model =
      modelConfigs.find((item) => item.id === modelConfigId) ??
      (!modelConfigId ? modelConfigs[0] : undefined);
    return model ? `${model.name} · ${model.model_id}` : "火山方舟默认模型";
  };

  const visible = agents.filter((agent) => {
    const text =
      `${agent.name} ${agent.description} ${agent.capabilities.map((item) => item.label).join(" ")}`.toLowerCase();
    return text.includes(query.toLowerCase());
  });

  const seedAgentDraftFromBrief = (brief: string) => {
    const value = brief.trim();
    if (!value) return;
    const compact = value
      .replace(/\s+/g, "")
      .replace(/[，。,.]/g, "")
      .slice(0, 14);
    const prompt = `你是${value}。请保持结构化、可验证、可执行，并在需要时调用已授权工具。`;
    if (!form.getFieldValue("name"))
      form.setFieldsValue({ name: `${compact || "自定义"} Agent` });
    if (!form.getFieldValue("description"))
      form.setFieldsValue({ description: value.slice(0, 180) });
    if (!form.getFieldValue("system_prompt")) {
      setSystemPrompt(prompt);
      form.setFieldsValue({ system_prompt: prompt });
    }
    if (!capabilities.length) {
      setCapabilities([
        { label: "任务分析", category: "通用", proficiency: 4 },
        { label: "结构化输出", category: "通用", proficiency: 4 },
      ]);
    }
  };

  const parseCapabilities = async () => {
    const text = String(
      form.getFieldValue("capability_text") ?? capabilityText ?? "",
    );
    const parsed = await api.parseCapabilities(text);
    setCapabilities(parsed.items);
    setSystemPrompt(parsed.system_prompt);
    form.setFieldsValue({ system_prompt: parsed.system_prompt });
  };

  const generateAgentDraft = async () => {
    const name = String(form.getFieldValue("name") ?? "");
    const description = String(form.getFieldValue("description") ?? "");
    const capabilityBrief = String(
      form.getFieldValue("capability_text") ?? capabilityText ?? "",
    );
    const brief = [name, description, capabilityBrief]
      .filter(Boolean)
      .join("\n");
    if (!brief.trim()) {
      message.warning("先输入 Agent 目标或职责描述");
      return;
    }
    const generated = await api.generateAgentConfig(
      brief,
      form.getFieldValue("base_agent_id"),
      form.getFieldValue("tools") ?? [],
    );
    setCapabilities(generated.capabilities);
    setSystemPrompt(generated.system_prompt);
    setCapabilityText(generated.capability_text ?? capabilityBrief);
    form.setFieldsValue({
      name: generated.name,
      description: generated.description,
      capability_text: generated.capability_text ?? capabilityBrief,
      system_prompt: generated.system_prompt,
      tools: generated.tools,
      temperature:
        generated.temperature ?? Number(generated.config?.temperature ?? 0.7),
    });
    message.success("AI 已生成 Agent 配置草稿");
  };

  const openEditAgent = (agent: Agent) => {
    setEditingAgent(agent);
    editForm.setFieldsValue({
      name: agent.name,
      display_name: agent.display_name,
      description: agent.description,
      status: agent.status,
      system_prompt: agent.config.custom_prompt_prefix,
      model_config_id: agent.config.model_config_id,
      tools: agent.config.tools ?? [],
      skill_ids: agent.config.skill_ids ?? [],
      mcp_server_ids: agent.config.mcp_server_ids ?? [],
      agentic_loop_enabled:
        agent.config.agentic_loop?.enabled ??
        Boolean(
          (agent.config.tools ?? []).length ||
          (agent.config.skill_ids ?? []).length ||
          (agent.config.mcp_server_ids ?? []).length,
        ),
      agentic_loop_steps: agent.config.agentic_loop?.max_steps ?? 2,
      temperature: agent.config.temperature ?? 0.7,
    });
  };

  const saveEditAgent = async () => {
    if (!editingAgent) return;
    const values = await editForm.validateFields();
    const updated = await api.updateAgent(editingAgent.id, {
      name: values.name,
      display_name: values.display_name,
      description: values.description,
      status: values.status,
      system_prompt: values.system_prompt,
      tools: values.tools ?? [],
      config: {
        temperature: values.temperature ?? 0.7,
        model_config_id: values.model_config_id,
        skill_ids: values.skill_ids ?? [],
        mcp_server_ids: values.mcp_server_ids ?? [],
        agentic_loop: {
          enabled: Boolean(values.agentic_loop_enabled),
          max_steps: values.agentic_loop_steps ?? 2,
          tool_policy: values.agentic_loop_enabled
            ? "agent_permissions"
            : "chat_only",
        },
      },
    });
    onUpdateAgent(updated);
    setEditingAgent(undefined);
    message.success("Agent 已更新");
  };

  const submit = async () => {
    const values = await form.validateFields();
    const created = await api.createAgent({
      name: values.name,
      description: values.description,
      capabilities,
      system_prompt: values.system_prompt,
      base_agent_id: values.base_agent_id,
      model_config_id: values.model_config_id,
      tools: values.tools ?? [],
      skill_ids: values.skill_ids ?? [],
      mcp_server_ids: values.mcp_server_ids ?? [],
      config: {
        temperature: values.temperature ?? 0.7,
        model_config_id: values.model_config_id,
        skill_ids: values.skill_ids ?? [],
        mcp_server_ids: values.mcp_server_ids ?? [],
        agentic_loop: {
          enabled: Boolean(values.agentic_loop_enabled),
          max_steps: values.agentic_loop_steps ?? 2,
          tool_policy: values.agentic_loop_enabled
            ? "agent_permissions"
            : "chat_only",
        },
      },
    });
    onCreateAgent(created);
    setCreatorOpen(false);
    message.success("自定义 Agent 已发布");
  };

  return (
    <>
      <Drawer
        width={720}
        title="Agent 广场与通讯录"
        open={open}
        onClose={onClose}
      >
        <Flex justify="space-between" align="center" className="drawer-toolbar">
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索名称、能力、描述"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Space>
            <Button onClick={onRefresh}>刷新状态</Button>
            <Button
              type="primary"
              icon={<RobotOutlined />}
              onClick={() => setCreatorOpen(true)}
              data-testid="create-agent"
            >
              创建自定义 Agent
            </Button>
          </Space>
        </Flex>
        <List
          grid={{ gutter: 12, column: 1 }}
          dataSource={visible}
          renderItem={(agent) => (
            <List.Item>
              <Card className="agent-card">
                <Flex justify="space-between" align="start">
                  <Space align="start">
                    <Badge
                      status={
                        agent.status === "online"
                          ? "success"
                          : agent.status === "degraded"
                            ? "warning"
                            : "default"
                      }
                      dot
                    >
                      <Avatar
                        style={{ background: agent.avatar_color ?? "#1677ff" }}
                      >
                        {agent.name.slice(0, 1)}
                      </Avatar>
                    </Badge>
                    <div>
                      <Space>
                        <Text strong>{agent.display_name ?? agent.name}</Text>
                        {agent.is_official && <Tag color="blue">官方</Tag>}
                        <Tag>{agent.type}</Tag>
                      </Space>
                      <Paragraph type="secondary" ellipsis={{ rows: 2 }}>
                        {agent.description}
                      </Paragraph>
                    </div>
                  </Space>
                  <Tag
                    color={agent.status === "online" ? "success" : "default"}
                  >
                    {agent.status}
                  </Tag>
                </Flex>
                <Space size={[4, 4]} wrap>
                  {agent.capabilities.slice(0, 4).map((cap) => (
                    <Tag key={cap.label}>
                      {cap.label}·{cap.proficiency}
                    </Tag>
                  ))}
                </Space>
                <Space size={[4, 4]} wrap className="mt-8">
                  {(agent.config.tools ?? []).slice(0, 5).map((tool) => (
                    <Tag key={tool} color="geekblue">
                      {tool}
                    </Tag>
                  ))}
                  {(agent.config.skill_ids ?? []).length > 0 && (
                    <Tag color="cyan">
                      {agent.config.skill_ids?.length} Skills
                    </Tag>
                  )}
                  {(agent.config.mcp_server_ids ?? []).length > 0 && (
                    <Tag color="gold">
                      {agent.config.mcp_server_ids?.length} MCP
                    </Tag>
                  )}
                  {agent.config.agentic_loop?.enabled === false && (
                    <Tag>纯对话</Tag>
                  )}
                  <Tag color="purple">
                    模型：{modelLabel(agent.config.model_config_id)}
                  </Tag>
                </Space>
                <Divider />
                <Flex justify="space-between">
                  <Text type="secondary">
                    {agent.response_latency_ms}ms · {agent.provider}
                  </Text>
                  <Space>
                    <Button
                      size="small"
                      onClick={() => {
                        setTestAgent(agent);
                        setTestResult("");
                        setTestError("");
                      }}
                    >
                      测试
                    </Button>
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => openEditAgent(agent)}
                      data-testid={`edit-agent-${agent.id}`}
                    >
                      编辑
                    </Button>
                    {!agent.is_official && (
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        data-testid={`delete-agent-${agent.id}`}
                        onClick={() => {
                          Modal.confirm({
                            title: `删除 Agent：${agent.name}`,
                            content:
                              "删除后不会再出现在 Agent 广场，也不能加入新会话。",
                            okText: "删除",
                            okButtonProps: { danger: true },
                            onOk: async () => {
                              await onDeleteAgent(agent);
                              message.success("Agent 已删除");
                            },
                          });
                        }}
                      />
                    )}
                  </Space>
                </Flex>
              </Card>
            </List.Item>
          )}
        />
      </Drawer>

      <Modal
        title="创建自定义 Agent"
        width={760}
        open={creatorOpen}
        onCancel={() => setCreatorOpen(false)}
        onOk={submit}
        okText="发布"
        okButtonProps={{ "data-testid": "agent-publish" }}
      >
        <Steps
          size="small"
          current={2}
          items={[
            { title: "基础信息" },
            { title: "能力解析" },
            { title: "提示词" },
            { title: "模型工具" },
            { title: "测试发布" },
          ]}
        />
        <Form
          form={form}
          layout="vertical"
          className="agent-form"
          initialValues={{
            temperature: 0.7,
            tools: ["file.read", "file.write", "file.extract_text"],
            skill_ids: [],
            mcp_server_ids: [],
            agentic_loop_enabled: true,
            agentic_loop_steps: 2,
          }}
          onValuesChange={(changed) => {
            if ("capability_text" in changed)
              setCapabilityText(String(changed.capability_text ?? ""));
            if ("system_prompt" in changed)
              setSystemPrompt(String(changed.system_prompt ?? ""));
          }}
        >
          <Form.Item
            name="name"
            label="Agent 名称"
            rules={[{ required: true, message: "请输入 Agent 名称" }]}
          >
            <Input maxLength={30} placeholder="数据库设计专家" />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
            rules={[{ required: true, message: "请输入描述" }]}
          >
            <TextArea rows={2} maxLength={500} />
          </Form.Item>
          <Form.Item name="capability_text" label="自然语言能力描述">
            <TextArea
              onChange={(event) => {
                setCapabilityText(event.target.value);
                seedAgentDraftFromBrief(event.target.value);
              }}
              onInput={(event) => {
                setCapabilityText(event.currentTarget.value);
                seedAgentDraftFromBrief(event.currentTarget.value);
              }}
              rows={3}
              data-testid="agent-capability-text"
            />
            <Space className="mt-8">
              <Button icon={<ToolOutlined />} onClick={parseCapabilities}>
                AI 解析能力标签
              </Button>
              <Button
                icon={<RobotOutlined />}
                onClick={generateAgentDraft}
                data-testid="ai-generate-agent"
              >
                AI 生成 Agent
              </Button>
            </Space>
          </Form.Item>
          <Space size={[4, 4]} wrap>
            {capabilities.map((cap) => (
              <Tag key={cap.label}>
                {cap.label} · {cap.category} · {cap.proficiency}
              </Tag>
            ))}
          </Space>
          <Form.Item
            name="system_prompt"
            label="系统提示词"
            rules={[{ required: true, message: "请配置系统提示词" }]}
          >
            <TextArea
              rows={5}
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
              data-testid="agent-system-prompt"
            />
          </Form.Item>
          <Form.Item name="base_agent_id" label="继承基础 Agent（可选）">
            <Select
              allowClear
              options={agents.map((agent) => ({
                label: agent.name,
                value: agent.id,
              }))}
            />
          </Form.Item>
          <Form.Item name="model_config_id" label="底层模型配置">
            <Select
              allowClear
              placeholder="使用系统默认豆包模型"
              options={modelConfigOptions}
            />
          </Form.Item>
          <Form.Item name="tools" label="工具权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择该 Agent 可调用的工具"
              optionFilterProp="label"
              options={toolOptions}
            />
          </Form.Item>
          <Form.Item name="skill_ids" label="Skill 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 Skills"
              optionFilterProp="label"
              options={skillOptions}
            />
          </Form.Item>
          <Form.Item name="mcp_server_ids" label="MCP 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 MCP 服务"
              optionFilterProp="label"
              options={mcpOptions}
            />
          </Form.Item>
          <Space align="start">
            <Form.Item
              name="agentic_loop_enabled"
              label="小循环模式"
              valuePropName="checked"
            >
              <Checkbox>允许短 Agentic Loop</Checkbox>
            </Form.Item>
            <Form.Item name="agentic_loop_steps" label="最大步数">
              <Select
                style={{ width: 120 }}
                options={[
                  { label: "1 步", value: 1 },
                  { label: "2 步", value: 2 },
                  { label: "3 步", value: 3 },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="temperature" label="Temperature">
            <Select
              options={[
                { label: "0.2 稳定", value: 0.2 },
                { label: "0.7 平衡", value: 0.7 },
                { label: "1.2 发散", value: 1.2 },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑 Agent：${editingAgent?.name ?? ""}`}
        width={720}
        open={Boolean(editingAgent)}
        onCancel={() => setEditingAgent(undefined)}
        onOk={saveEditAgent}
        okText="保存"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label="Agent 名称"
            rules={[{ required: true }]}
          >
            <Input maxLength={30} />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input maxLength={30} />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
            rules={[{ required: true }]}
          >
            <TextArea rows={3} maxLength={500} />
          </Form.Item>
          <Form.Item
            name="system_prompt"
            label="系统提示词"
            rules={[{ required: true }]}
          >
            <TextArea rows={5} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              options={[
                { label: "online", value: "online" },
                { label: "offline", value: "offline" },
                { label: "degraded", value: "degraded" },
                { label: "maintenance", value: "maintenance" },
              ]}
            />
          </Form.Item>
          <Form.Item name="model_config_id" label="底层模型配置">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="使用系统默认豆包模型"
              options={modelConfigOptions}
            />
          </Form.Item>
          <Form.Item name="tools" label="工具权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择该 Agent 可调用的工具"
              optionFilterProp="label"
              options={toolOptions}
            />
          </Form.Item>
          <Form.Item name="skill_ids" label="Skill 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 Skills"
              optionFilterProp="label"
              options={skillOptions}
            />
          </Form.Item>
          <Form.Item name="mcp_server_ids" label="MCP 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 MCP 服务"
              optionFilterProp="label"
              options={mcpOptions}
            />
          </Form.Item>
          <Space align="start">
            <Form.Item
              name="agentic_loop_enabled"
              label="小循环模式"
              valuePropName="checked"
            >
              <Checkbox>允许短 Agentic Loop</Checkbox>
            </Form.Item>
            <Form.Item name="agentic_loop_steps" label="最大步数">
              <Select
                style={{ width: 120 }}
                options={[
                  { label: "1 步", value: 1 },
                  { label: "2 步", value: 2 },
                  { label: "3 步", value: 3 },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="temperature" label="Temperature">
            <Select
              options={[
                { label: "0.2 稳定", value: 0.2 },
                { label: "0.7 平衡", value: 0.7 },
                { label: "1.2 发散", value: 1.2 },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`测试 Agent：${testAgent?.name ?? ""}`}
        open={Boolean(testAgent)}
        onCancel={() => setTestAgent(undefined)}
        footer={null}
      >
        <Space direction="vertical" className="full-width">
          <TextArea
            value={testText}
            onChange={(event) => setTestText(event.target.value)}
            rows={3}
          />
          <Button
            type="primary"
            loading={testLoading}
            onClick={async () => {
              if (!testAgent) return;
              setTestLoading(true);
              setTestError("");
              setTestResult("正在等待模型回复...");
              try {
                setTestResult(await onTestAgent(testAgent.id, testText));
              } catch (error) {
                setTestResult("");
                setTestError(
                  error instanceof Error ? error.message : "连接失败",
                );
              } finally {
                setTestLoading(false);
              }
            }}
          >
            发送测试
          </Button>
          {testLoading && (
            <Text type="secondary">
              正在等待回复，真实模型可能需要几秒钟...
            </Text>
          )}
          {testError && (
            <Card className="result-box error-box">连接失败：{testError}</Card>
          )}
          {testResult && <Card>{testResult}</Card>}
        </Space>
      </Modal>
    </>
  );
}
