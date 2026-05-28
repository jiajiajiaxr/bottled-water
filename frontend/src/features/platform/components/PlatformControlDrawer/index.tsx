import {
  App as AntApp,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Drawer,
  Empty,
  Flex,
  Form,
  Input,
  List,
  Modal,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
} from "antd";
import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  RocketOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../../../api";
import type {
  AuditLog,
  Conversation,
  ConversationWorkflow,
  McpInvocation,
  McpServer,
  ModelConfig,
  ModelProvider,
  Project,
  RemoteConnection,
  SandboxCommandResult,
  SandboxSession,
  SecurityRole,
  SecurityUser,
  Skill,
  ToolDefinition,
  WorkflowRun,
  Workspace,
} from "../../../../types";
import { formatTime } from "../../../../lib/format";

const { TextArea } = Input;

interface PlatformControlDrawerProps {
  open: boolean;
  workspaces: Workspace[];
  activeConversation?: Conversation;
  onClose: () => void;
  onCreateWorkspace: (payload: {
    name: string;
    description: string;
    type: string;
    tags: string[];
    config?: Record<string, unknown>;
  }) => Promise<void>;
  onCreateProject: (
    workspaceId: string,
    payload: { name: string; description: string; type: string },
  ) => Promise<Project>;
  onLoadProjects: (workspaceId: string) => Promise<Project[]>;
  onSaveProjectFile: (
    projectId: string,
    payload: { path: string; language: string; content: string },
  ) => Promise<void>;
}

export function PlatformControlDrawer({
  open,
  workspaces,
  activeConversation,
  onClose,
  onCreateWorkspace,
  onCreateProject,
  onLoadProjects,
  onSaveProjectFile,
}: PlatformControlDrawerProps) {
  const [workspaceForm] = Form.useForm();
  const [projectForm] = Form.useForm();
  const [fileForm] = Form.useForm();
  const [providerForm] = Form.useForm();
  const [modelForm] = Form.useForm();
  const [mcpForm] = Form.useForm();
  const [mcpImportForm] = Form.useForm();
  const [skillForm] = Form.useForm();
  const [skillImportForm] = Form.useForm();
  const [toolForm] = Form.useForm();
  const [toolGenerateForm] = Form.useForm();
  const [sandboxForm] = Form.useForm();
  const [commandForm] = Form.useForm();
  const [remoteForm] = Form.useForm();
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>();
  const [modelProviders, setModelProviders] = useState<ModelProvider[]>([]);
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [_mcpInvocations, setMcpInvocations] = useState<McpInvocation[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [sandboxes, setSandboxes] = useState<SandboxSession[]>([]);
  const [selectedSandbox, setSelectedSandbox] = useState<string>();
  const [remoteConnections, setRemoteConnections] = useState<
    RemoteConnection[]
  >([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [securityRoles, setSecurityRoles] = useState<SecurityRole[]>([]);
  const [securityUsers, setSecurityUsers] = useState<SecurityUser[]>([]);
  const [auditStats, setAuditStats] = useState<{
    total: number;
    high_risk: number;
    by_action: Record<string, number>;
  }>();
  const [modelTestResult, setModelTestResult] = useState("");
  const [skillTestResult, setSkillTestResult] = useState("");
  const [skillSearch, setSkillSearch] = useState("");
  const [toolInvokeResult, setToolInvokeResult] = useState("");
  const [sandboxResult, setSandboxResult] = useState<SandboxCommandResult>();
  const [_mcpInvocationResult, setMcpInvocationResult] = useState("");
  const [routingMode, setRoutingMode] = useState("auto");
  const [_workflowStatus, setWorkflowStatus] = useState("ready");
  const [conversationWorkflow, setConversationWorkflow] =
    useState<ConversationWorkflow>();
  const [workflowJson, setWorkflowJson] = useState("");
  const [draggingNodeId, setDraggingNodeId] = useState<string>();
  const [_workflowRuns, setWorkflowRuns] = useState<WorkflowRun[]>([]);
  const { message } = AntApp.useApp();

  const activeWorkspace =
    workspaces.find((item) => item.id === selectedWorkspace) ?? workspaces[0];
  const selectedSandboxSession = useMemo(
    () => sandboxes.find((item) => item.id === selectedSandbox),
    [sandboxes, selectedSandbox],
  );
  const filteredSkills = useMemo(() => {
    const keyword = skillSearch.trim().toLowerCase();
    if (!keyword) return skills;
    return skills.filter((skill) =>
      [
        skill.name,
        skill.description,
        skill.category,
        skill.scope,
        skill.source,
        ...(skill.tools ?? []),
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword)),
    );
  }, [skills, skillSearch]);

  const parseList = (value?: string) =>
    String(value ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

  const loadProjects = async () => {
    if (!activeWorkspace) return;
    setProjects(await onLoadProjects(activeWorkspace.id));
  };

  const loadPlatformResources = async () => {
    const [
      providers,
      configs,
      servers,
      nextSkills,
      nextTools,
      sessions,
      remotes,
      invocations,
      logs,
      roles,
      users,
      stats,
    ] = await Promise.all([
      api.modelProviders(),
      api.modelConfigs(),
      api.mcpServers(activeWorkspace?.id),
      api.skills(activeWorkspace?.id),
      api.tools(activeWorkspace?.id),
      api.sandboxes(),
      api.remoteConnections(),
      api.mcpInvocations().catch(() => []),
      api.auditLogs().catch(() => []),
      api.securityRoles().catch(() => []),
      api.securityUsers().catch(() => []),
      api.auditStats().catch(() => undefined),
    ]);
    setModelProviders(providers);
    setModelConfigs(configs);
    setMcpServers(servers);
    setMcpInvocations(invocations);
    setSkills(nextSkills);
    setTools(nextTools);
    setSandboxes(sessions);
    setRemoteConnections(remotes);
    setAuditLogs(logs);
    setSecurityRoles(roles);
    setSecurityUsers(users);
    setAuditStats(stats);
    if (!selectedSandbox && sessions[0]) setSelectedSandbox(sessions[0].id);
  };

  const loadConversationWorkflow = async () => {
    if (!activeConversation?.id) {
      setConversationWorkflow(undefined);
      setWorkflowJson("");
      return;
    }
    const workflow = await api.conversationWorkflow(activeConversation.id);
    const runs = await api.workflowRuns(activeConversation.id).catch(() => []);
    setConversationWorkflow(workflow);
    setWorkflowJson(JSON.stringify(workflow, null, 2));
    setWorkflowRuns(runs);
  };

  useEffect(() => {
    if (!selectedWorkspace && workspaces[0])
      setSelectedWorkspace(workspaces[0].id);
  }, [workspaces, selectedWorkspace]);

  useEffect(() => {
    if (open) {
      loadProjects();
      loadPlatformResources();
      loadConversationWorkflow();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeWorkspace?.id, activeConversation?.id]);

  const workflowIcon = (role?: string) => {
    if (role === "input") return <MessageOutlined />;
    if (role === "master") return <BranchesOutlined />;
    if (role === "reviewer") return <CheckCircleOutlined />;
    if (role === "artifact") return <RocketOutlined />;
    return <RobotOutlined />;
  };
  const workflowNodes = conversationWorkflow?.nodes ?? [];
  const workflowEdges = (conversationWorkflow?.edges ?? []) as Array<[string, string]>;

  const setWorkflowDraft = (next: ConversationWorkflow) => {
    setConversationWorkflow(next);
    setWorkflowJson(JSON.stringify(next, null, 2));
  };

  const reorderWorkflowNode = (sourceId: string, targetId: string) => {
    if (!conversationWorkflow || sourceId === targetId) return;
    const nodes = [...conversationWorkflow.nodes];
    const from = nodes.findIndex((node) => node.id === sourceId);
    const to = nodes.findIndex((node) => node.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = nodes.splice(from, 1);
    nodes.splice(to, 0, moved);
    const edges = nodes
      .slice(1)
      .map((node, index) => [nodes[index].id, node.id]);
    setWorkflowDraft({ ...conversationWorkflow, nodes, edges });
  };

  return (
    <Drawer
      title="工作区与平台控制面"
      width={1040}
      open={open}
      onClose={onClose}
    >
      <Flex justify="space-between" align="center" className="drawer-toolbar">
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder="选择工作区"
            value={activeWorkspace?.id}
            onChange={setSelectedWorkspace}
            options={workspaces.map((workspace) => ({
              label: workspace.name,
              value: workspace.id,
            }))}
          />
          {activeWorkspace && (
            <>
              <Tag color="blue">{activeWorkspace.type}</Tag>
              <Tag>{activeWorkspace.status}</Tag>
              <Tag>{activeWorkspace.member_count} 成员</Tag>
              <Tag>{activeWorkspace.project_count} 项目</Tag>
            </>
          )}
        </Space>
        <Button icon={<ReloadOutlined />} onClick={loadPlatformResources}>
          刷新
        </Button>
      </Flex>
      <Tabs
        items={[
          {
            key: "assets",
            label: "资产",
            children: (
              <>
                <div className="workspace-grid">
                  <Card title="创建工作区">
                    <Form
                      form={workspaceForm}
                      layout="vertical"
                      initialValues={{
                        type: "vertical",
                        tags: "fullstack,demo",
                        template_id: "fullstack-delivery",
                      }}
                      onFinish={async (values) => {
                        await onCreateWorkspace({
                          name: values.name,
                          description: values.description ?? "",
                          type: values.type,
                          tags: parseList(values.tags),
                          config: { template_id: values.template_id },
                        });
                        workspaceForm.resetFields();
                      }}
                    >
                      <Form.Item
                        name="name"
                        label="名称"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="业务增长工作区" />
                      </Form.Item>
                      <Form.Item name="description" label="描述">
                        <Input />
                      </Form.Item>
                      <Space align="start">
                        <Form.Item name="type" label="类型">
                          <Select
                            style={{ width: 150 }}
                            options={[
                              { label: "垂直业务", value: "vertical" },
                              { label: "跨团队", value: "cross" },
                              { label: "自定义", value: "custom" },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item name="template_id" label="模板">
                          <Select
                            style={{ width: 180 }}
                            options={[
                              {
                                label: "全链路开发",
                                value: "fullstack-delivery",
                              },
                              { label: "数据分析", value: "data-analysis" },
                              { label: "自定义实验", value: "custom-lab" },
                            ]}
                          />
                        </Form.Item>
                      </Space>
                      <Form.Item name="tags" label="标签">
                        <Input placeholder="逗号分隔" />
                      </Form.Item>
                      <Button type="primary" htmlType="submit">
                        创建工作区
                      </Button>
                    </Form>
                  </Card>
                  <Card title="资源概览">
                    <List
                      dataSource={workspaces}
                      renderItem={(workspace) => (
                        <List.Item
                          className={
                            workspace.id === activeWorkspace?.id
                              ? "workspace-active"
                              : ""
                          }
                          onClick={() => setSelectedWorkspace(workspace.id)}
                        >
                          <List.Item.Meta
                            avatar={
                              <Avatar style={{ background: "#1677ff" }}>
                                {workspace.name.slice(0, 1)}
                              </Avatar>
                            }
                            title={
                              <Space>
                                <strong>{workspace.name}</strong>
                                <Tag>{workspace.type}</Tag>
                                <Tag>{workspace.status}</Tag>
                              </Space>
                            }
                            description={`${workspace.member_count} 成员 · ${workspace.project_count} 项目 · ${workspace.tags.join("/")}`}
                          />
                        </List.Item>
                      )}
                    />
                  </Card>
                </div>
                <Divider />
                <div className="workspace-grid">
                  <Card title="创建项目">
                    <Form
                      form={projectForm}
                      layout="vertical"
                      initialValues={{ type: "code_project" }}
                      onFinish={async (values) => {
                        if (!activeWorkspace) return;
                        const project = await onCreateProject(
                          activeWorkspace.id,
                          values,
                        );
                        setProjects((current) => [project, ...current]);
                        setSelectedProject(project.id);
                        projectForm.resetFields();
                      }}
                    >
                      <Form.Item
                        name="name"
                        label="项目名称"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="agenthub-preview" />
                      </Form.Item>
                      <Form.Item name="description" label="描述">
                        <Input />
                      </Form.Item>
                      <Form.Item name="type" label="项目类型">
                        <Select
                          options={[
                            { label: "代码工程", value: "code_project" },
                            { label: "业务文档", value: "document" },
                            { label: "交互页面", value: "web_app" },
                          ]}
                        />
                      </Form.Item>
                      <Button htmlType="submit" disabled={!activeWorkspace}>
                        创建项目
                      </Button>
                    </Form>
                  </Card>
                  <Card title="项目文件快照">
                    <Select
                      className="full-width"
                      placeholder="选择项目"
                      value={selectedProject}
                      onChange={setSelectedProject}
                      options={projects.map((project) => ({
                        label: `${project.name} · v${project.current_version}`,
                        value: project.id,
                      }))}
                    />
                    <Form
                      className="mt-8"
                      form={fileForm}
                      layout="vertical"
                      initialValues={{
                        path: "src/main.ts",
                        language: "typescript",
                        content: "export const demo = true;",
                      }}
                      onFinish={async (values) => {
                        if (!selectedProject) return;
                        await onSaveProjectFile(selectedProject, values);
                        fileForm.resetFields();
                      }}
                    >
                      <Form.Item
                        name="path"
                        label="路径"
                        rules={[{ required: true }]}
                      >
                        <Input />
                      </Form.Item>
                      <Form.Item name="language" label="语言">
                        <Input />
                      </Form.Item>
                      <Form.Item name="content" label="内容">
                        <TextArea rows={4} />
                      </Form.Item>
                      <Button disabled={!selectedProject} htmlType="submit">
                        保存文件版本
                      </Button>
                    </Form>
                  </Card>
                </div>
              </>
            ),
          },
          {
            key: "workflow",
            label: "工作流画布",
            children: (
              <div className="workflow-board">
                <div className="workflow-canvas">
                  {workflowNodes.length ? (
                    workflowNodes.map((node, index) => (
                      <div
                        key={node.id}
                        className={`workflow-node workflow-node-${node.status}`}
                        draggable
                        onDragStart={() => setDraggingNodeId(node.id)}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={() => {
                          if (draggingNodeId)
                            reorderWorkflowNode(draggingNodeId, node.id);
                          setDraggingNodeId(undefined);
                        }}
                      >
                        <div className="workflow-node-icon">
                          {workflowIcon(node.role)}
                        </div>
                        <div className="workflow-node-body">
                          <strong>{node.title}</strong>
                          <span className="ant-typography ant-typography-secondary">{node.meta}</span>
                        </div>
                        {index < workflowNodes.length - 1 && (
                          <div className="workflow-arrow">→</div>
                        )}
                      </div>
                    ))
                  ) : (
                    <Empty description="选择一个会话后，可按群聊 Agent 自动生成工作流" />
                  )}
                </div>
                <div className="workflow-side">
                  <Card title="会话工作流">
                    <Space direction="vertical" className="full-width">
                      <span className="ant-typography ant-typography-secondary">
                        {activeConversation
                          ? activeConversation.title
                          : "暂无选中会话"}
                      </span>
                      <Space wrap>
                        <Button
                          icon={<RobotOutlined />}
                          disabled={!activeConversation}
                          onClick={async () => {
                            if (!activeConversation) return;
                            const workflow =
                              await api.generateConversationWorkflow(
                                activeConversation.id,
                              );
                            setConversationWorkflow(workflow);
                            setWorkflowJson(JSON.stringify(workflow, null, 2));
                            message.success("AI 已按当前群聊 Agent 生成工作流");
                          }}
                        >
                          AI 生成
                        </Button>
                        <Button
                          icon={<CheckCircleOutlined />}
                          disabled={!activeConversation || !workflowJson.trim()}
                          onClick={async () => {
                            if (!activeConversation) return;
                            let workflow: ConversationWorkflow;
                            try {
                              workflow = JSON.parse(
                                workflowJson,
                              ) as ConversationWorkflow;
                            } catch {
                              message.error("工作流 JSON 格式不正确");
                              return;
                            }
                            const saved = await api.saveConversationWorkflow(
                              activeConversation.id,
                              workflow,
                            );
                            setConversationWorkflow(saved);
                            setWorkflowJson(JSON.stringify(saved, null, 2));
                            message.success("工作流已保存");
                          }}
                        >
                          保存
                        </Button>
                      </Space>
                      <Button
                        icon={<PlusOutlined />}
                        disabled={!conversationWorkflow}
                        onClick={() => {
                          if (!conversationWorkflow) return;
                          const id = `node-${Date.now().toString(36)}`;
                          const nodes = [
                            ...conversationWorkflow.nodes,
                            {
                              id,
                              title: "New node",
                              role: "worker",
                              status: "ready",
                              meta: "Manual step",
                            },
                          ];
                          const edges = nodes
                            .slice(1)
                            .map((node, index) => [nodes[index].id, node.id]);
                          setWorkflowDraft({
                            ...conversationWorkflow,
                            nodes,
                            edges,
                          });
                        }}
                      >
                        Add node
                      </Button>
                      <Button
                        icon={<BranchesOutlined />}
                        disabled={!activeConversation || !conversationWorkflow}
                        onClick={async () => {
                          if (!activeConversation || !conversationWorkflow)
                            return;
                          const run = await api.startWorkflowRun(
                            activeConversation.id,
                            conversationWorkflow,
                          );
                          setWorkflowRuns((current) => [run, ...current]);
                          message.success("Workflow run started");
                        }}
                      >
                        Run
                      </Button>
                      <TextArea
                        rows={10}
                        value={workflowJson}
                        onChange={(event) =>
                          setWorkflowJson(event.target.value)
                        }
                        placeholder="工作流 JSON：nodes / edges / settings"
                      />
                    </Space>
                  </Card>
                  <Card title="调度参数" className="mt-8">
                    <Space direction="vertical" className="full-width">
                      <Segmented
                        block
                        value={routingMode}
                        onChange={(value) => setRoutingMode(String(value))}
                        options={[
                          { label: "自动", value: "auto" },
                          { label: "人工确认", value: "human" },
                          { label: "成本优先", value: "cost" },
                        ]}
                      />
                      <Select
                        defaultValue="review-required"
                        options={[
                          {
                            label: "Reviewer 必须通过",
                            value: "review-required",
                          },
                          { label: "低风险跳过", value: "risk-based" },
                          { label: "双 Reviewer", value: "dual-review" },
                        ]}
                      />
                      <Select
                        defaultValue="summary-window"
                        options={[
                          { label: "摘要滚动窗口", value: "summary-window" },
                          { label: "全量上下文", value: "full-context" },
                          { label: "知识库优先", value: "kb-first" },
                        ]}
                      />
                      <Button
                        type="primary"
                        icon={<BranchesOutlined />}
                        onClick={() => {
                          setWorkflowStatus("running");
                          setConversationWorkflow((current) =>
                            current
                              ? {
                                  ...current,
                                  nodes: current.nodes.map((node) =>
                                    node.role === "master"
                                      ? { ...node, status: "running" }
                                      : node,
                                  ),
                                }
                              : current,
                          );
                          window.setTimeout(() => {
                            setWorkflowStatus("ready");
                            setConversationWorkflow((current) =>
                              current
                                ? {
                                    ...current,
                                    nodes: current.nodes.map((node) =>
                                      node.role === "master"
                                        ? { ...node, status: "ready" }
                                        : node,
                                    ),
                                  }
                                : current,
                            );
                          }, 1200);
                          message.success(`调度演练已触发：${routingMode}`);
                        }}
                      >
                        调度演练
                      </Button>
                    </Space>
                  </Card>
                  <Card title="依赖连线" className="mt-8">
                    <List
                      size="small"
                      dataSource={workflowEdges}
                      renderItem={([from, to]) => (
                        <List.Item>
                          <Tag>{from}</Tag>
                          <span>→</span>
                          <Tag color="blue">{to}</Tag>
                        </List.Item>
                      )}
                    />
                  </Card>
                </div>
              </div>
            ),
          },
          {
            key: "models",
            label: "模型",
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
                      const provider = await api.createModelProvider({
                        ...values,
                        supports_streaming: Boolean(values.supports_streaming),
                        supports_embeddings: Boolean(
                          values.supports_embeddings,
                        ),
                      });
                      setModelProviders((current) => [provider, ...current]);
                      providerForm.resetFields(["name", "api_key"]);
                      message.success("模型供应商已创建");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="我的 OpenAI 兼容模型" />
                    </Form.Item>
                    <Form.Item name="provider_type" label="类型">
                      <Select
                        options={[
                          {
                            label: "OpenAI Compatible",
                            value: "openai-compatible",
                          },
                          { label: "火山方舟", value: "ark" },
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
                      <Input.Password placeholder="仅提交到后端保存，前端不回显" />
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
                    <Button type="primary" htmlType="submit">
                      保存供应商
                    </Button>
                  </Form>
                </Card>
                <Card title="模型配置与测试">
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
                        <Input placeholder="Reviewer 模型" />
                      </Form.Item>
                      <Form.Item
                        name="model_id"
                        label="模型 ID"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="doubao-seed-1-6" />
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
                    enterButton="测试"
                    onSearch={async (prompt) => {
                      const currentModel = modelConfigs[0];
                      const result = await api.testModel(
                        prompt || "请回复模型已就绪。",
                        currentModel?.id,
                      );
                      setModelTestResult(`${result.model}: ${result.response}`);
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
                              <strong>{model.name}</strong>
                              <Tag>{model.purpose}</Tag>
                              <Tag>{model.status}</Tag>
                            </Space>
                          }
                          description={`${model.provider_name ?? model.provider_id} · ${model.model_id} · ${model.context_window} tokens`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
          {
            key: "mcp",
            label: "MCP",
            children: (
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
            ),
          },
          {
            key: "tools",
            label: "工具",
            children: (
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
            ),
          },
          {
            key: "skills",
            label: "Skills",
            children: (
              <div className="workspace-grid">
                <Card title="创建 Skill">
                  <Form
                    form={skillForm}
                    layout="vertical"
                    initialValues={{
                      scope: "workspace",
                      category: "workflow",
                      tools: "file.read,browser.open",
                    }}
                    onFinish={async (values) => {
                      const skill = await api.createSkill({
                        workspace_id: activeWorkspace?.id,
                        name: values.name,
                        description: values.description ?? "",
                        category: values.category,
                        scope: values.scope,
                        prompt_template: values.prompt_template,
                        tools: parseList(values.tools),
                        enabled: true,
                      });
                      setSkills((current) => [skill, ...current]);
                      skillForm.resetFields([
                        "name",
                        "description",
                        "prompt_template",
                      ]);
                      message.success("Skill 已创建");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="Skill 名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="前端审查 Skill" />
                    </Form.Item>
                    <Form.Item name="description" label="描述">
                      <Input />
                    </Form.Item>
                    <Space align="start">
                      <Form.Item name="category" label="分类">
                        <Input style={{ width: 160 }} />
                      </Form.Item>
                      <Form.Item name="scope" label="范围">
                        <Select
                          style={{ width: 160 }}
                          options={[
                            { label: "工作区", value: "workspace" },
                            { label: "平台", value: "platform" },
                            { label: "个人", value: "personal" },
                          ]}
                        />
                      </Form.Item>
                    </Space>
                    <Form.Item name="prompt_template" label="Prompt 模板">
                      <TextArea rows={4} />
                    </Form.Item>
                    <Form.Item name="tools" label="工具">
                      <Input placeholder="逗号分隔，如 file.read,browser.open" />
                    </Form.Item>
                    <Space>
                      <Button
                        type="primary"
                        htmlType="submit"
                        disabled={!activeWorkspace}
                      >
                        保存 Skill
                      </Button>
                      <Button
                        icon={<RobotOutlined />}
                        data-testid="ai-generate-skill"
                        disabled={!activeWorkspace}
                        onClick={async () => {
                          const values = skillForm.getFieldsValue();
                          const intent = [
                            values.name,
                            values.description,
                            values.prompt_template,
                          ]
                            .filter(Boolean)
                            .join("\n");
                          if (!intent.trim()) {
                            message.warning("先输入 Skill 名称、描述或目标");
                            return;
                          }
                          const skill = await api.generateSkill({
                            workspace_id: activeWorkspace?.id,
                            name: values.name,
                            intent,
                            requirements: values.prompt_template ?? "",
                            category: values.category || "ai",
                            tags: parseList(values.tools),
                          });
                          setSkills((current) => [skill, ...current]);
                          skillForm.setFieldsValue({
                            name: skill.name,
                            description: skill.description,
                            category: skill.category,
                            prompt_template: skill.prompt_template,
                            tools: skill.tools.join(","),
                          });
                          message.success("AI 已创建 Skill");
                        }}
                      >
                        AI 创建 Skill
                      </Button>
                    </Space>
                  </Form>
                </Card>
                <Card title="Skill 目录">
                  <Flex
                    justify="space-between"
                    align="center"
                    wrap="wrap"
                    gap={8}
                    style={{ marginBottom: 12 }}
                  >
                    <Input.Search
                      allowClear
                      style={{ maxWidth: 340 }}
                      placeholder="搜索 Skill 名称、分类或工具"
                      value={skillSearch}
                      onChange={(event) => setSkillSearch(event.target.value)}
                    />
                    <Space>
                      <Tag>
                        {filteredSkills.length}/{skills.length} Skills
                      </Tag>
                      <Button
                        icon={<ReloadOutlined />}
                        onClick={loadPlatformResources}
                      >
                        刷新
                      </Button>
                    </Space>
                  </Flex>
                  <Form
                    form={skillImportForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      const skill = await api.importMcpAsSkill({
                        workspace_id: activeWorkspace?.id,
                        mcp_server_id: values.mcp_server_id,
                        name: values.name,
                        category: "mcp",
                      });
                      setSkills((current) => [skill, ...current]);
                      skillImportForm.resetFields(["name"]);
                      message.success("已从 MCP 导入 Skill");
                    }}
                  >
                    <Form.Item
                      name="mcp_server_id"
                      label="MCP 服务"
                      rules={[{ required: true }]}
                    >
                      <Select
                        placeholder="选择已注册 MCP"
                        options={mcpServers.map((server) => ({
                          label: `${server.name} · ${server.transport}`,
                          value: server.id,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name="name" label="Skill 名称">
                      <Input placeholder="留空则使用 MCP 名称" />
                    </Form.Item>
                    <Button
                      htmlType="submit"
                      icon={<ToolOutlined />}
                      disabled={!mcpServers.length}
                    >
                      从 MCP 导入 Skill
                    </Button>
                  </Form>
                  <Divider />
                  {skillTestResult && (
                    <div className="result-box">{skillTestResult}</div>
                  )}
                  <List
                    dataSource={filteredSkills}
                    locale={{ emptyText: "暂无 Skills" }}
                    renderItem={(skill) => (
                      <List.Item
                        actions={[
                          <Button
                            key="test"
                            size="small"
                            onClick={async () => {
                              const result = await api.testSkill(
                                skill.id,
                                `请测试 ${skill.name} 是否可用，并用一句话说明。`,
                              );
                              setSkillTestResult(
                                `${result.model}: ${result.response}`,
                              );
                            }}
                          >
                            测试
                          </Button>,
                          (skill.created_by ||
                            skill.workspace_id === activeWorkspace?.id) &&
                            !skill.config?.builtin && (
                              <Button
                                key="delete"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => {
                                  Modal.confirm({
                                    title: `删除 Skill：${skill.name}`,
                                    content:
                                      "删除后将不再出现在当前工作区 Skill 目录，也不能再授权给 Agent 使用。",
                                    okText: "删除",
                                    okButtonProps: { danger: true },
                                    onOk: async () => {
                                      try {
                                        await api.deleteSkill(skill.id);
                                        setSkills((current) =>
                                          current.filter(
                                            (item) => item.id !== skill.id,
                                          ),
                                        );
                                        setSkillTestResult("");
                                        message.success("Skill 已删除");
                                      } catch (error) {
                                        message.error(
                                          error instanceof Error
                                            ? error.message
                                            : "删除失败",
                                        );
                                        throw error;
                                      }
                                    },
                                  });
                                }}
                              >
                                删除
                              </Button>
                            ),
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<Avatar icon={<ToolOutlined />} />}
                          title={
                            <Space>
                              <strong>{skill.name}</strong>
                              <Tag>{skill.category}</Tag>
                              <Tag
                                color={skill.workspace_id ? "purple" : "blue"}
                              >
                                {skill.workspace_id ? "工作区" : "全局"}
                              </Tag>
                              {Boolean(skill.config?.builtin) && (
                                <Tag color="geekblue">内置</Tag>
                              )}
                              <Tag
                                color={skill.enabled ? "success" : "default"}
                              >
                                {skill.enabled ? "enabled" : "disabled"}
                              </Tag>
                              {skill.source === "mcp" && (
                                <Tag color="blue">MCP</Tag>
                              )}
                            </Space>
                          }
                          description={
                            <Space direction="vertical" size={4}>
                              <span className="ant-typography ant-typography-secondary">
                                {skill.description || "暂无描述"}
                              </span>
                              <Space size={[4, 4]} wrap>
                                {(skill.tools ?? []).map((tool) => (
                                  <Tag key={tool}>{tool}</Tag>
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
            ),
          },
          {
            key: "security",
            label: "Security",
            children: (
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
            ),
          },
          {
            key: "sandbox",
            label: "沙箱/远程",
            children: (
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
                  {selectedSandboxSession && (
                    <div className="mt-8">
                      <Space wrap size={[4, 4]}>
                        <Tag>{selectedSandboxSession.status}</Tag>
                        {selectedSandboxSession.workspace_id && (
                          <Tag>workspace: {selectedSandboxSession.workspace_id}</Tag>
                        )}
                        {selectedSandboxSession.project_id && (
                          <Tag>project: {selectedSandboxSession.project_id}</Tag>
                        )}
                        {selectedSandboxSession.last_command_at && (
                          <Tag>last: {formatTime(selectedSandboxSession.last_command_at)}</Tag>
                        )}
                      </Space>
                    </div>
                  )}
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
                      <Space wrap size={[4, 4]}>
                        <Tag>{sandboxResult.status || "completed"}</Tag>
                        <Tag>exit {sandboxResult.exit_code}</Tag>
                        <Tag>{sandboxResult.duration_ms}ms</Tag>
                      </Space>
                      <div>{sandboxResult.command}</div>
                      {sandboxResult.cwd && <small>{sandboxResult.cwd}</small>}
                      <pre>
                        {[sandboxResult.stdout, sandboxResult.stderr]
                          .filter(Boolean)
                          .join("\n")}
                      </pre>
                    </div>
                  )}
                  {selectedSandboxSession?.mounted_files?.length ? (
                    <>
                      <Divider />
                      <List
                        size="small"
                        header="工作目录文件"
                        dataSource={selectedSandboxSession.mounted_files.slice(0, 8)}
                        renderItem={(file) => (
                          <List.Item>
                            <List.Item.Meta
                              title={file.path}
                              description={`${file.size} bytes`}
                            />
                          </List.Item>
                        )}
                      />
                    </>
                  ) : null}
                  {selectedSandboxSession?.command_history?.length ? (
                    <>
                      <Divider />
                      <List
                        size="small"
                        header="最近运行记录"
                        dataSource={selectedSandboxSession.command_history.slice(0, 6)}
                        renderItem={(item) => (
                          <List.Item>
                            <List.Item.Meta
                              title={
                                <Space>
                                  <span>{item.command}</span>
                                  <Tag>{item.status || item.exit_code}</Tag>
                                </Space>
                              }
                              description={item.cwd || item.created_at}
                            />
                          </List.Item>
                        )}
                      />
                    </>
                  ) : null}
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
                              const updated = await api.connectRemote(
                                remote.id,
                              );
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
            ),
          },
        ].filter((item) => !["workflow", "models"].includes(String(item.key)))}
      />
    </Drawer>
  );
}
