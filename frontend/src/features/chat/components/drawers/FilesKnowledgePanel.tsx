import { useState } from "react";
import {
  Button,
  Card,
  Divider,
  Form,
  Input,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
} from "antd";
import type { UploadedFile, KnowledgeBase } from "@/types";

const { TextArea } = Input;

export function FilesKnowledgePanel({
  files,
  knowledgeBases,
  onCreateKb,
  onImportText,
  onRetrieve,
}: {
  files: UploadedFile[];
  knowledgeBases: KnowledgeBase[];
  onCreateKb: (payload: {
    name: string;
    description: string;
    scope: string;
    visibility: string;
  }) => Promise<void>;
  onImportText: (
    kbId: string,
    payload: { title: string; content: string },
  ) => Promise<void>;
  onRetrieve: (kbId: string, query: string) => Promise<string>;
}) {
  const [kbForm] = Form.useForm();
  const [docForm] = Form.useForm();
  const [query, setQuery] = useState("");
  const [selectedKb, setSelectedKb] = useState<string>();
  const [retrieveResult, setRetrieveResult] = useState("");

  return (
    <Tabs
      items={[
        {
          key: "files",
          label: "文件",
          children: (
            <Table
              size="small"
              pagination={false}
              dataSource={files}
              rowKey="id"
              columns={[
                { title: "文件名", dataIndex: "original_filename" },
                {
                  title: "大小",
                  dataIndex: "size",
                  render: (value: number) => `${Math.ceil(value / 1024)}KB`,
                },
                {
                  title: "状态",
                  dataIndex: "parse_status",
                  render: (value: string) => <Tag>{value}</Tag>,
                },
              ]}
            />
          ),
        },
        {
          key: "knowledge",
          label: "知识库",
          children: (
            <Space direction="vertical" className="full-width">
              <Form
                form={kbForm}
                layout="vertical"
                onFinish={onCreateKb}
                initialValues={{ scope: "personal", visibility: "private" }}
              >
                <Form.Item
                  name="name"
                  label="知识库名称"
                  rules={[{ required: true }]}
                >
                  <Input
                    placeholder="项目需求知识库"
                    data-testid="knowledge-create"
                  />
                </Form.Item>
                <Form.Item name="description" label="描述">
                  <Input />
                </Form.Item>
                <Space>
                  <Form.Item name="scope" label="范围">
                    <Select
                      style={{ width: 140 }}
                      options={[
                        { label: "个人", value: "personal" },
                        { label: "工作区", value: "workspace" },
                        { label: "平台", value: "platform" },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="visibility" label="可见性">
                    <Select
                      style={{ width: 140 }}
                      options={[
                        { label: "私有", value: "private" },
                        { label: "公开", value: "public" },
                      ]}
                    />
                  </Form.Item>
                </Space>
                <Button htmlType="submit" type="primary">
                  创建知识库
                </Button>
              </Form>
              <Divider />
              <Select
                placeholder="选择知识库"
                value={selectedKb}
                onChange={setSelectedKb}
                options={knowledgeBases.map((kb) => ({
                  label: `${kb.name} · ${kb.document_count} 文档`,
                  value: kb.id,
                }))}
                className="full-width"
              />
              <Form
                form={docForm}
                layout="vertical"
                onFinish={(values) =>
                  selectedKb && onImportText(selectedKb, values)
                }
              >
                <Form.Item
                  name="title"
                  label="导入文档标题"
                  rules={[{ required: true }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="content"
                  label="文档内容"
                  rules={[{ required: true }]}
                >
                  <TextArea rows={4} />
                </Form.Item>
                <Button disabled={!selectedKb} htmlType="submit">
                  导入并索引
                </Button>
              </Form>
              <Divider />
              <Input.Search
                placeholder="检索知识库"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onSearch={async () =>
                  selectedKb &&
                  setRetrieveResult(await onRetrieve(selectedKb, query))
                }
                enterButton="检索"
                disabled={!selectedKb}
              />
              {retrieveResult && <Card>{retrieveResult}</Card>}
            </Space>
          ),
        },
      ]}
    />
  );
}
