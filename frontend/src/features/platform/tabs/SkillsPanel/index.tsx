import { useEffect, useMemo, useState } from "react";
import {
  App as AntApp,
  Avatar,
  Button,
  Card,
  Divider,
  Flex,
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
  ReloadOutlined,
  RobotOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { api } from "@/api";
import { parseList } from "@/lib/format";
import type { McpServer, Skill, Workspace } from "@/types";

const { TextArea } = Input;

interface SkillsPanelProps {
  activeWorkspace?: Workspace;
}

export function SkillsPanel({ activeWorkspace }: SkillsPanelProps) {
  const { message } = AntApp.useApp();
  const [skillForm] = Form.useForm();
  const [skillImportForm] = Form.useForm();

  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillSearch, setSkillSearch] = useState("");
  const [skillTestResult, setSkillTestResult] = useState("");
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);

  const load = async () => {
    try {
      const [nextSkills, servers] = await Promise.all([
        api.skills(activeWorkspace?.id).catch(() => []),
        api.mcpServers(activeWorkspace?.id).catch(() => []),
      ]);
      setSkills(nextSkills);
      setMcpServers(servers);
    } catch {
      message.error("加载 Skills 数据失败");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace?.id]);

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

  return (
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
            <Button icon={<ReloadOutlined />} onClick={load}>
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
  );
}
