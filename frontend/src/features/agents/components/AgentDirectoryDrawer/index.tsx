import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftOutlined,
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
import { api } from "../../../../api";
import type {
  Agent,
  AgentCapability,
  McpServer,
  ModelConfig,
  Skill,
  ToolDefinition,
} from "../../../../types";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

export function AgentDirectoryDrawer({
  open,
  asPage,
  agents,
  onClose,
  onRefresh,
  onCreateAgent,
  onUpdateAgent,
  onDeleteAgent,
  onTestAgent,
}: {
  open?: boolean;
  asPage?: boolean;
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
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const createDefaultsAppliedRef = useRef(false);
  const { message } = AntApp.useApp();
  const createToolValues = Form.useWatch("tools", form) as string[] | undefined;
  const editToolValues = Form.useWatch("tools", editForm) as string[] | undefined;
  const createSkillValues = Form.useWatch("skill_ids", form) as string[] | undefined;
  const editSkillValues = Form.useWatch("skill_ids", editForm) as string[] | undefined;
  const createMcpValues = Form.useWatch("mcp_server_ids", form) as string[] | undefined;
  const editMcpValues = Form.useWatch("mcp_server_ids", editForm) as string[] | undefined;
  const createAvatarUrl = Form.useWatch("avatar_url", form) as string | undefined;
  const editAvatarUrl = Form.useWatch("avatar_url", editForm) as string | undefined;

  const catalogToolNames = useMemo(
    () => dedupeToolCatalog(toolCatalog).map((tool) => tool.name),
    [toolCatalog],
  );
  const catalogSkillIds = useMemo(
    () => skills.map((skill) => skill.id),
    [skills],
  );
  const catalogMcpServerIds = useMemo(
    () => mcpServers.map((server) => server.id),
    [mcpServers],
  );
  const hasExplicitCapabilityPermissions = (agent?: Agent) =>
    Boolean(agent?.config.capability_permissions_initialized);
  const permissionValuesForAgent = (agent?: Agent) => {
    if (hasExplicitCapabilityPermissions(agent)) {
      return {
        tools: agent?.config.tools ?? [],
        skill_ids: agent?.config.skill_ids ?? [],
        mcp_server_ids: agent?.config.mcp_server_ids ?? [],
      };
    }
    return {
      tools: catalogToolNames,
      skill_ids: catalogSkillIds,
      mcp_server_ids: catalogMcpServerIds,
    };
  };

  useEffect(() => {
    if (!open && !asPage) return;
    let cancelled = false;
    setCatalogLoading(true);
    setCatalogError("");
    Promise.allSettled([
      api.modelConfigs(),
      api.tools(),
      api.skills(),
      api.mcpServers(),
    ])
      .then(([configs, tools, nextSkills, servers]) => {
        if (cancelled) return;
        const failures = [configs, tools, nextSkills, servers].filter(
          (result) => result.status === "rejected",
        );
        if (failures.length) {
          setCatalogError("能力目录加载失败，请刷新后重试");
          message.error("能力目录加载失败，请刷新后重试");
        }
        setModelConfigs(configs.status === "fulfilled" ? configs.value : []);
        setToolCatalog(tools.status === "fulfilled" ? tools.value : []);
        setSkills(nextSkills.status === "fulfilled" ? nextSkills.value : []);
        setMcpServers(servers.status === "fulfilled" ? servers.value : []);
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [asPage, message, open]);

  useEffect(() => {
    if (!creatorOpen) {
      createDefaultsAppliedRef.current = false;
      return;
    }
    if (catalogLoading || createDefaultsAppliedRef.current) return;
    if (form.isFieldsTouched(["tools", "skill_ids", "mcp_server_ids"])) return;
    form.setFieldsValue({
      tools: catalogToolNames,
      skill_ids: catalogSkillIds,
      mcp_server_ids: catalogMcpServerIds,
      agentic_loop_enabled: true,
    });
    createDefaultsAppliedRef.current = true;
  }, [catalogLoading, catalogMcpServerIds, catalogSkillIds, catalogToolNames, creatorOpen, form]);

  useEffect(() => {
    if (!editingAgent || catalogLoading) return;
    if (editForm.isFieldsTouched(["tools", "skill_ids", "mcp_server_ids"])) return;
    editForm.setFieldsValue(permissionValuesForAgent(editingAgent));
  }, [catalogLoading, catalogMcpServerIds, catalogSkillIds, catalogToolNames, editForm, editingAgent]);

  const selectedToolValues = useMemo(
    () =>
      Array.from(
        new Set([
          ...(createToolValues ?? []),
          ...(editToolValues ?? []),
          ...(editingAgent?.config.tools ?? []),
        ]),
      ),
    [createToolValues, editToolValues, editingAgent],
  );
  const selectedSkillValues = useMemo(
    () =>
      Array.from(
        new Set([
          ...(createSkillValues ?? []),
          ...(editSkillValues ?? []),
          ...(editingAgent?.config.skill_ids ?? []),
        ]),
      ),
    [createSkillValues, editSkillValues, editingAgent],
  );
  const selectedMcpValues = useMemo(
    () =>
      Array.from(
        new Set([
          ...(createMcpValues ?? []),
          ...(editMcpValues ?? []),
          ...(editingAgent?.config.mcp_server_ids ?? []),
        ]),
      ),
    [createMcpValues, editMcpValues, editingAgent],
  );

  const toolOptions = useMemo(() => {
    const dedupedCatalog = dedupeToolCatalog(toolCatalog);
    const known = new Set(dedupedCatalog.map((tool) => tool.name));
    return [
      ...dedupedCatalog.map((tool) => ({
        label: `${tool.display_name ?? tool.name} · ${tool.name}`,
        value: tool.name,
      })),
      ...selectedToolValues
        .filter((name) => name && !known.has(name))
        .map((name) => ({
          label: `旧配置：${name}`,
          value: name,
          disabled: true,
        })),
    ];
  }, [selectedToolValues, toolCatalog]);
  const skillOptions = useMemo(() => {
    const known = new Set(skills.map((skill) => skill.id));
    return [
      ...skills.map((skill) => ({
        label: `${skill.name} · ${skill.category}`,
        value: skill.id,
      })),
      ...selectedSkillValues
        .filter((id) => id && !known.has(id))
        .map((id) => ({ label: `旧 Skill：${id}`, value: id, disabled: true })),
    ];
  }, [selectedSkillValues, skills]);
  const mcpOptions = useMemo(() => {
    const known = new Set(mcpServers.map((server) => server.id));
    return [
      ...mcpServers.map((server) => ({
        label: `${server.name} · ${server.transport}`,
        value: server.id,
      })),
      ...selectedMcpValues
        .filter((id) => id && !known.has(id))
        .map((id) => ({ label: `旧 MCP：${id}`, value: id, disabled: true })),
    ];
  }, [mcpServers, selectedMcpValues]);
  const modelConfigOptions = useMemo(
    () =>
      modelConfigs.map((model) => ({
        label: `${model.name} · ${model.model_id}`,
        value: model.id,
      })),
    [modelConfigs],
  );
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
      tools: form.getFieldValue("tools") ?? catalogToolNames,
      temperature:
        generated.temperature ?? Number(generated.config?.temperature ?? 0.7),
    });
    message.success("AI 已生成 Agent 配置草稿");
  };

  const openEditAgent = (agent: Agent) => {
    setEditingAgent(agent);
    const permissionValues = permissionValuesForAgent(agent);
    editForm.setFieldsValue({
      name: agent.name,
      display_name: agent.display_name,
      avatar_url: agent.avatar_url,
      description: agent.description,
      status: agent.status,
      system_prompt: agent.config.custom_prompt_prefix,
      model_config_id: agent.config.model_config_id,
      tools: permissionValues.tools,
      skill_ids: permissionValues.skill_ids,
      mcp_server_ids: permissionValues.mcp_server_ids,
      agentic_loop_enabled:
        agent.config.agentic_loop?.enabled ??
        Boolean(
          permissionValues.tools.length ||
          permissionValues.skill_ids.length ||
          permissionValues.mcp_server_ids.length,
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
      avatar_url: values.avatar_url,
      description: values.description,
      status: values.status,
      system_prompt: values.system_prompt,
      tools: values.tools ?? [],
      config: {
        temperature: values.temperature ?? 0.7,
        model_config_id: values.model_config_id,
        capability_permissions_initialized: true,
        tools: values.tools ?? [],
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
      avatar_url: values.avatar_url,
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
        capability_permissions_initialized: true,
        tools: values.tools ?? [],
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

  const mainContent = (
    <>
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
                      src={agent.avatar_url}
                      icon={!agent.avatar_url ? <RobotOutlined /> : undefined}
                      style={{ background: agent.avatar_color ?? "#1677ff" }}
                    />
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
              <Flex justify="end">
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
    </>
  );

  return (
    <>
      {asPage ? (
        <div className="page-view">
          <div className="page-header">
            <Button
              icon={<ArrowLeftOutlined />}
              onClick={onClose}
            >
              返回
            </Button>
            <Text strong>Agent 广场与通讯录</Text>
          </div>
          <div className="page-content">{mainContent}</div>
        </div>
      ) : (
        <Drawer
          width={720}
          title="Agent 广场与通讯录"
          open={open}
          onClose={onClose}
        >
          {mainContent}
        </Drawer>
      )}

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
            tools: catalogToolNames,
            skill_ids: catalogSkillIds,
            mcp_server_ids: catalogMcpServerIds,
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
          <Form.Item name="avatar_url" label="Agent 头像 URL">
            <Flex align="center" gap={12}>
              <Avatar
                size={48}
                src={createAvatarUrl}
                icon={!createAvatarUrl ? <RobotOutlined /> : undefined}
                style={{ background: "#1677ff" }}
              />
              <Input allowClear placeholder="https://example.com/avatar.png" />
            </Flex>
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
              loading={catalogLoading}
              options={modelConfigOptions}
            />
          </Form.Item>
          <Form.Item name="tools" label="工具权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择该 Agent 可调用的工具"
              optionFilterProp="label"
              loading={catalogLoading}
              notFoundContent={catalogError || undefined}
              options={toolOptions}
            />
          </Form.Item>
          <Form.Item name="skill_ids" label="Skill 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 Skills"
              optionFilterProp="label"
              loading={catalogLoading}
              notFoundContent={catalogError || undefined}
              options={skillOptions}
            />
          </Form.Item>
          <Form.Item name="mcp_server_ids" label="MCP 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 MCP 服务"
              optionFilterProp="label"
              loading={catalogLoading}
              notFoundContent={catalogError || undefined}
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
          <Form.Item name="avatar_url" label="Agent 头像 URL">
            <Flex align="center" gap={12}>
              <Avatar
                size={48}
                src={editAvatarUrl}
                icon={!editAvatarUrl ? <RobotOutlined /> : undefined}
                style={{ background: editingAgent?.avatar_color ?? "#1677ff" }}
              />
              <Input allowClear placeholder="https://example.com/avatar.png" />
            </Flex>
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
              loading={catalogLoading}
              options={modelConfigOptions}
            />
          </Form.Item>
          <Form.Item name="tools" label="工具权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择该 Agent 可调用的工具"
              optionFilterProp="label"
              loading={catalogLoading}
              notFoundContent={catalogError || undefined}
              options={toolOptions}
            />
          </Form.Item>
          <Form.Item name="skill_ids" label="Skill 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 Skills"
              optionFilterProp="label"
              loading={catalogLoading}
              notFoundContent={catalogError || undefined}
              options={skillOptions}
            />
          </Form.Item>
          <Form.Item name="mcp_server_ids" label="MCP 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 MCP 服务"
              optionFilterProp="label"
              loading={catalogLoading}
              notFoundContent={catalogError || undefined}
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

function dedupeToolCatalog(catalog: ToolDefinition[]) {
  const byName = new Map<string, ToolDefinition>();
  const byBuiltinDisplay = new Map<string, ToolDefinition>();

  for (const tool of catalog) {
    const existing = byName.get(tool.name);
    if (!existing || preferTool(tool, existing)) {
      byName.set(tool.name, tool);
    }
  }

  for (const tool of byName.values()) {
    const key = `${tool.display_name ?? tool.name}::${tool.category ?? ""}`;
    const existing = byBuiltinDisplay.get(key);
    if (!existing || preferTool(tool, existing)) {
      byBuiltinDisplay.set(key, tool);
    }
  }

  return [...byBuiltinDisplay.values()];
}

function preferTool(candidate: ToolDefinition, current: ToolDefinition) {
  if (candidate.is_builtin && !current.is_builtin) return true;
  if (!candidate.created_by && current.created_by) return true;
  return false;
}
