import { useEffect, useState } from "react";
import {
  CheckCircleOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DiffOutlined,
  EditOutlined,
  EyeOutlined,
  LinkOutlined,
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
  Tooltip,
  Typography,
} from "antd";
import { api } from "@/api";
import { diffLines } from "@/lib/diff";
import { buildPreviewDocument } from "@/lib/preview";
import { FilesKnowledgePanel } from "@/features/chat/components/drawers/FilesKnowledgePanel";
import {
  artifactExportFormats,
  downloadLabel,
  openOrDownloadExport,
  preferredArtifactFormat,
} from "./artifactPreview";
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
  onDeploy: () => Promise<Deployment | undefined> | Deployment | undefined | void;
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
  const [previewFile, setPreviewFile] = useState<{
    previewUrl?: string;
    contentType: string;
    filename?: string;
  }>();
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [latestDeployment, setLatestDeployment] = useState<
    Deployment | undefined
  >(deployment);
  const [deploying, setDeploying] = useState(false);

  useEffect(() => {
    setLatestDeployment(deployment);
  }, [deployment]);

  useEffect(() => {
    if (!artifact?.id) {
      setLatestDeployment(undefined);
      return;
    }

    let cancelled = false;
    api
      .deploymentsForArtifact(artifact.id)
      .then((result) => {
        if (cancelled) return;
        setLatestDeployment(result.items?.[0] ?? deployment);
      })
      .catch(() => {
        if (!cancelled) setLatestDeployment(deployment);
      });

    return () => {
      cancelled = true;
    };
  }, [artifact?.id, deployment]);

  useEffect(() => {
    const previewHtml =
      artifact?.content?.preview_html ||
      artifact?.content?.files?.["preview.html"] ||
      artifact?.content?.files?.["index.html"] ||
      artifact?.code ||
      "";
    setDraft(previewHtml);
  }, [artifact?.id, artifact?.code, artifact?.content]);

  useEffect(() => {
    if (!artifact) return;
    setPreviewFile(undefined);
    setPreviewError("");
    if (artifactPreviewKind(artifact) !== "pdf") return;
    let cancelled = false;
    setPreviewLoading(true);
    api.previewArtifactPdf(artifact.id)
      .then((result) => {
        if (cancelled) return;
        if (!result.previewUrl) {
          setPreviewError("预览接口没有返回可显示的 PDF 内容");
          return;
        }
        setPreviewFile({
          previewUrl: result.previewUrl,
          contentType: result.contentType,
          filename: result.filename,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        setPreviewError(
          error instanceof Error ? error.message : "产物预览加载失败",
        );
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [artifact]);

  useEffect(() => {
    return () => {
      if (previewFile?.previewUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(previewFile.previewUrl);
      }
    };
  }, [previewFile?.previewUrl]);

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
  const previewKind = artifactPreviewKind(artifact);
  const preferredFormat = preferredArtifactFormat(artifact);
  const exportFormats = artifactExportFormats(preferredFormat);
  const currentDeployment = latestDeployment ?? deployment;
  const deploymentUrl =
    currentDeployment?.url || currentDeployment?.access_url || "";
  const deploymentCommit = currentDeployment?.commit ?? currentDeployment?.id?.slice(0, 8);

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
        {exportFormats.map((format) => (
          <Button
            key={format}
            size="small"
            type="primary"
            onClick={async () => {
              const exported = await api.exportArtifact(artifact.id, format);
              setExportResult(exported);
              openOrDownloadExport(exported, format);
            }}
          >
            {downloadLabel(format)}
          </Button>
        ))}
        {exportResult?.filename && (
          <Tag color="blue">{exportResult.filename}</Tag>
        )}
      </Space>
      <Text type="secondary" className="preview-tab-hint">
        图标说明：预览效果、编辑源码、Diff 对比、部署预览、文件与知识库。
      </Text>
      <Tabs
        data-testid="artifact-tabs"
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: "preview",
            label: (
              <Tooltip title="预览效果：查看渲染页面、PDF 或 Office 转换预览">
                <EyeOutlined aria-label="预览效果" />
              </Tooltip>
            ),
            children: (
              <div className="preview-frame-wrap">
                {previewKind === "pdf" ? (
                  previewLoading ? (
                    <Empty description="正在生成预览..." />
                  ) : previewFile?.previewUrl ? (
                    <iframe
                      title="artifact pdf preview"
                      src={previewFile.previewUrl}
                    />
                  ) : (
                    <Empty
                      description={
                        previewError || "当前产物暂时无法在线预览，请下载原文件"
                      }
                    />
                  )
                ) : (
                  <iframe
                    title="artifact preview"
                    sandbox="allow-scripts"
                    srcDoc={previewDocument}
                  />
                )}
              </div>
            ),
          },
          {
            key: "code",
            label: (
              <Tooltip title="编辑源码：查看和修改当前产物内容">
                <CodeOutlined aria-label="编辑源码" />
              </Tooltip>
            ),
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
            label: (
              <Tooltip title="Diff 对比：查看当前修改和上一版本的差异">
                <DiffOutlined aria-label="Diff 对比" />
              </Tooltip>
            ),
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
            label: (
              <Tooltip title="部署预览：创建或查看当前产物的可访问部署地址">
                <RocketOutlined aria-label="部署预览" />
              </Tooltip>
            ),
            children: (
              <Card className="deploy-card" data-testid="deployment-card">
                <Space direction="vertical" size={14}>
                  <Tag
                    color={
                      currentDeployment?.status === "ready" ||
                      currentDeployment?.status === "deployed"
                        ? "success"
                        : "processing"
                    }
                    icon={<RocketOutlined />}
                  >
                    {currentDeployment?.status ?? "idle"}
                  </Tag>
                  {deploymentUrl ? (
                    <Text strong copyable>
                      {deploymentUrl}
                    </Text>
                  ) : (
                  <Text strong>{deployment?.url ?? "尚未部署"}</Text>
                  )}
                  <Text type="secondary">
                    Commit: {deploymentCommit ?? "pending"}
                  </Text>
                  <Progress percent={currentDeployment ? 100 : 0} size="small" />
                  <Space wrap>
                    <Button
                      type="primary"
                      icon={<RocketOutlined />}
                      loading={deploying}
                      onClick={async () => {
                        setDeploying(true);
                        try {
                          const next = await onDeploy();
                          if (next) setLatestDeployment(next);
                        } finally {
                          setDeploying(false);
                        }
                      }}
                      data-testid="deploy-artifact"
                    >
                      部署当前版本
                    </Button>
                    {deploymentUrl && (
                      <Button
                        icon={<LinkOutlined />}
                        href={deploymentUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        打开访问 URL
                      </Button>
                    )}
                  </Space>
                </Space>
              </Card>
            ),
          },
          {
            key: "assets",
            label: (
              <Tooltip title="文件与知识库：查看关联文件、导入知识库或检索资料">
                <DatabaseOutlined aria-label="文件与知识库" />
              </Tooltip>
            ),
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

function artifactPreviewKind(artifact: WorkspaceArtifact): "html" | "pdf" {
  const format = String(
    artifact.content?.format ||
      artifact.content?.tool_output?.format ||
      artifact.format ||
      artifact.filename?.split(".").pop() ||
      "",
  ).toLowerCase();
  const mediaType = String(
    artifact.content?.media_type || artifact.media_type || "",
  ).toLowerCase();
  if (
    ["pdf", "docx", "pptx", "xlsx"].includes(format) ||
    mediaType.includes("pdf") ||
    mediaType.includes("officedocument")
  ) {
    return "pdf";
  }
  return "html";
}
