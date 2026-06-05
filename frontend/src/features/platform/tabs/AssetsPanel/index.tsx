import { useEffect, useState } from "react";
import {
  App as AntApp,
  Avatar,
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
import { api } from "@/api";
import { parseList } from "@/lib/format";
import type { Project, Workspace } from "@/types";

const { TextArea } = Input;

interface AssetsPanelProps {
  workspaces: Workspace[];
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

export function AssetsPanel({
  workspaces,
  onCreateWorkspace,
  onCreateProject,
  onLoadProjects,
  onSaveProjectFile,
}: AssetsPanelProps) {
  const { message } = AntApp.useApp();
  const [workspaceForm] = Form.useForm();
  const [projectForm] = Form.useForm();
  const [fileForm] = Form.useForm();

  const [selectedWorkspace, setSelectedWorkspace] = useState<string>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>();

  const activeWorkspace =
    workspaces.find((item) => item.id === selectedWorkspace) ?? workspaces[0];

  useEffect(() => {
    if (!selectedWorkspace && workspaces[0]) {
      setSelectedWorkspace(workspaces[0].id);
    }
  }, [workspaces, selectedWorkspace]);

  useEffect(() => {
    if (!activeWorkspace) return;
    onLoadProjects(activeWorkspace.id).then(setProjects);
  }, [activeWorkspace, onLoadProjects]);

  return (
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
  );
}
