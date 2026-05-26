import { useEffect, useState } from "react";
import {
  CheckCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DiffOutlined,
  EditOutlined,
  EyeOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import {
  Button,
  Card,
  Empty,
  Flex,
  Input,
  Layout,
  Progress,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { api } from "@/api";
import { diffLines } from "@/lib/diff";
import { buildPreviewDocument } from "@/lib/preview";
import { FilesKnowledgePanel } from "@/features/chat/components/drawers/FilesKnowledgePanel";
import type {
  Deployment,
  KnowledgeBase,
  UploadedFile,
  WorkspaceArtifact,
} from "@/types";

const { Sider } = Layout;
const { TextArea } = Input;
const { Title, Text } = Typography;

export function PreviewPanel({
  artifact,
  deployment,
  files,
  knowledgeBases,
  onClose,
  onSave,
  onDeploy,
  onCreateKb,
  onImportText,
  onRetrieve,
}: {
  artifact?: WorkspaceArtifact;
  deployment?: Deployment;
  files: UploadedFile[];
  knowledgeBases: KnowledgeBase[];
  onClose: () => void;
  onSave: (artifact: WorkspaceArtifact) => void;
  onDeploy: () => void;
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
  const [tab, setTab] = useState("preview");
  const [draft, setDraft] = useState("");
  const [exportResult, setExportResult] = useState<{
    previewUrl?: string;
    previewText?: string;
    contentType: string;
    filename?: string;
  }>();

  useEffect(() => {
    setDraft(artifact?.code ?? "");
  }, [artifact?.id, artifact?.code]);

  if (!artifact) {
    return (
      <Sider
        width={460}
        className="preview-panel"
        data-testid="artifact-preview-panel"
      >
        <Empty description="点击聊天流中的预览产物卡片后展开预览、编辑、Diff、部署和资产面板" />
      </Sider>
    );
  }

  const previewDocument = buildPreviewDocument(draft);

  return (
    <Sider
      width={470}
      className="preview-panel"
      data-testid="artifact-preview-panel"
    >
      <Flex justify="space-between" align="center" className="preview-head">
        <div>
          <Text type="secondary">Artifact</Text>
          <Title level={4}>{artifact.title}</Title>
        </div>
        <Space>
          <Button onClick={onClose}>Close</Button>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={() => onSave({ ...artifact, code: draft })}
            data-testid="save-artifact"
          >
            保存
          </Button>
        </Space>
      </Flex>
      <Space wrap className="artifact-export-bar">
        {["zip", "html", "markdown", "json", "docx", "xlsx", "pptx"].map(
          (format) => (
            <Button
              key={format}
              size="small"
              onClick={async () => {
                const exported = await api.exportArtifact(artifact.id, format);
                setExportResult(exported);
                if (exported.previewUrl)
                  window.open(
                    exported.previewUrl,
                    "_blank",
                    "noopener,noreferrer",
                  );
              }}
            >
              {format.toUpperCase()}
            </Button>
          ),
        )}
        {exportResult?.filename && (
          <Tag color="blue">{exportResult.filename}</Tag>
        )}
      </Space>
      <Tabs
        data-testid="artifact-tabs"
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: "preview",
            label: <EyeOutlined />,
            children: (
              <div className="preview-frame-wrap">
                <iframe
                  title="artifact preview"
                  sandbox="allow-scripts"
                  srcDoc={previewDocument}
                />
              </div>
            ),
          },
          {
            key: "code",
            label: <CodeOutlined />,
            children: (
              <div className="code-pane">
                <Flex justify="space-between" align="center">
                  <Tag icon={<EditOutlined />}>Textarea fallback</Tag>
                  <Text type="secondary">{artifact.language}</Text>
                </Flex>
                <TextArea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  className="code-editor"
                  data-testid="artifact-code-editor"
                  aria-label="artifact-code-editor"
                />
              </div>
            ),
          },
          {
            key: "diff",
            label: <DiffOutlined />,
            children: (
              <div className="diff-pane">
                {diffLines(artifact.previousCode, draft).map((line, index) => (
                  <div
                    key={`${line.type}-${index}`}
                    className={`diff-line diff-${line.type}`}
                  >
                    <span>
                      {line.type === "add"
                        ? "+"
                        : line.type === "remove"
                          ? "-"
                          : line.type === "change"
                            ? "~"
                            : " "}
                    </span>
                    <code>{line.text}</code>
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: "deploy",
            label: <RocketOutlined />,
            children: (
              <Card className="deploy-card" data-testid="deployment-card">
                <Space direction="vertical" size={14}>
                  <Tag
                    color={
                      deployment?.status === "ready" ||
                      deployment?.status === "deployed"
                        ? "success"
                        : "processing"
                    }
                    icon={<RocketOutlined />}
                  >
                    {deployment?.status ?? "idle"}
                  </Tag>
                  <Text strong>{deployment?.url ?? "尚未部署"}</Text>
                  <Text type="secondary">
                    Commit: {deployment?.commit ?? "pending"}
                  </Text>
                  <Progress percent={deployment ? 100 : 0} size="small" />
                  <Button
                    type="primary"
                    icon={<RocketOutlined />}
                    onClick={onDeploy}
                    data-testid="deploy-artifact"
                  >
                    部署当前版本
                  </Button>
                </Space>
              </Card>
            ),
          },
          {
            key: "assets",
            label: <DatabaseOutlined />,
            children: (
              <FilesKnowledgePanel
                files={files}
                knowledgeBases={knowledgeBases}
                onCreateKb={onCreateKb}
                onImportText={onImportText}
                onRetrieve={onRetrieve}
              />
            ),
          },
        ]}
      />
    </Sider>
  );
}
