import React, { useEffect, useState } from "react";
import {
  BranchesOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  EyeOutlined,
  FileImageOutlined,
  LoadingOutlined,
  MessageOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Button,
  Flex,
  Modal,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { api } from "@/api";
import { formatFileSize, formatTime } from "@/lib/format";
import { MarkdownContent } from "@/lib/markdown";
import {
  attachmentName,
  messageAttachments,
  stripInternalAgentOutput,
} from "@/lib/message";
import type { ChatMessage, CodeRunRecord, MessageAttachment } from "@/types";
import ThinkingBlock from "./ThinkingBlock";
import { TerminalToolCards } from "./TerminalToolCards";
import { ToolCallSummary } from "./ToolCallSummary";

const { Text, Paragraph } = Typography;

interface MessageBubbleProps {
  message: ChatMessage;
  workspaceId?: string;
  currentUserAvatarUrl?: string;
  version?: number;
  quoted?: ChatMessage;
  onQuote?: (message: ChatMessage) => void;
  onCopy?: (text: string) => void;
  onPreview?: (message: ChatMessage) => void;
}

function MessageBubbleComponent({
  message,
  workspaceId,
  currentUserAvatarUrl,
  quoted,
  onQuote,
  onCopy,
  onPreview,
}: MessageBubbleProps) {
  const author = message.author || "未知";
  const isUser = message.role === "user";
  const senderAvatarUrl =
    typeof message.sender_avatar_url === "string"
      ? message.sender_avatar_url
      : undefined;
  const userAvatarUrl = senderAvatarUrl || currentUserAvatarUrl;
  const agentAvatarUrl =
    senderAvatarUrl ??
    (typeof message.rawContent?.agent_avatar_url === "string"
      ? message.rawContent.agent_avatar_url
      : undefined);
  const isEvent =
    message.kind === "event" ||
    message.role === "system" ||
    message.role === "tool";
  const attachments = messageAttachments(message);
  const [previewAttachment, setPreviewAttachment] = useState<
    | (MessageAttachment & {
        previewUrl?: string;
        previewText?: string;
        contentType?: string;
        downloadUrl?: string;
        previewError?: string;
      })
    | undefined
  >();
  const [previewLoading, setPreviewLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    return () => {
      if (previewAttachment?.previewUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(previewAttachment.previewUrl);
      }
    };
  }, [previewAttachment?.previewUrl]);

  const openAttachment = async (attachment: MessageAttachment) => {
    const image = isImageAttachment(attachment);
    const directUrl = attachment.public_url ?? attachment.url;
    const next = {
      ...attachment,
      contentType: attachment.content_type,
      previewText: attachment.extracted_text,
      previewUrl: directUrl,
      downloadUrl: attachment.download_url,
    };
    setPreviewAttachment(next);
    const fileId = attachment.file_id ?? attachment.id;
    if (
      !fileId ||
      (!image && (attachment.extracted_text || directUrl)) ||
      (image && directUrl)
    ) {
      return;
    }
    setPreviewLoading(true);
    try {
      const preview = await api.previewFile(fileId);
      setPreviewAttachment((current) =>
        current ? { ...current, ...preview } : current,
      );
    } catch (error) {
      setPreviewAttachment((current) =>
        current
          ? {
              ...current,
              previewError:
                error instanceof Error ? error.message : "附件预览失败",
            }
          : current,
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  if (isEvent) {
    return (
      <div className="event-message">
        <Tag icon={<BranchesOutlined />}>{author}</Tag>
        <Text type="secondary">{message.content}</Text>
      </div>
    );
  }

  if (message.kind === "preview_card") {
    return (
      <div className="message-row from-agent">
        <Avatar
          className="message-avatar"
          src={agentAvatarUrl}
          icon={!agentAvatarUrl ? <RobotOutlined /> : undefined}
        />
        <button
          type="button"
          className="message-card preview-message-card preview-card-button"
          data-testid="preview-card"
          onClick={() => onPreview?.(message)}
        >
          <Flex justify="space-between" align="center">
            <Space>
              <EyeOutlined />
              <Text strong>{message.content}</Text>
            </Space>
            <Tag color="blue">预览产物</Tag>
          </Flex>
          <Paragraph type="secondary">
            产物已生成，点击打开右侧预览、编辑、Diff 对比和部署。
          </Paragraph>
        </button>
      </div>
    );
  }

  const previewType =
    previewAttachment?.contentType ?? previewAttachment?.content_type ?? "";
  const previewUrl =
    previewAttachment?.previewUrl ??
    previewAttachment?.public_url ??
    previewAttachment?.url;
  const visibleMessageContent = stripInternalAgentOutput(message.content);
  const thinkingText = String(message.thinking || "").trim();
  const streamThinkingEnabled = message.rawContent?._streamThinkingEnabled === true;
  const messageThinkingEnabled =
    message.rawContent?.thinking_enabled === true ||
    streamThinkingEnabled;
  const showThinkingBlock = Boolean(
    !isUser &&
    messageThinkingEnabled &&
    thinkingText,
  );
  const activeToolCalls = message.rawContent?._activeToolCalls as
    | Array<{ toolName: string }>
    | undefined;
  const codeRunResults = codeRunsFromMessage(message);
  const runCodeBlock = async (
    index: number,
    language: string,
    code: string,
  ): Promise<CodeRunRecord> => {
    return await api.runMessageCodeBlock(message.conversationId, message.id, {
      language,
      code,
      index,
      timeout_seconds: 10,
      workspace_id: workspaceId,
      conversation_id: message.conversationId,
      message_id: message.id,
    });
  };

  return (
    <>
      <div className={`message-row ${isUser ? "from-user" : "from-agent"}`}>
        <Avatar
          className="message-avatar"
          src={isUser ? userAvatarUrl : agentAvatarUrl}
          icon={!isUser && !agentAvatarUrl ? <RobotOutlined /> : undefined}
        >
          {isUser && !userAvatarUrl ? author.slice(0, 1) : undefined}
        </Avatar>
        <div className="message-card">
          <Flex justify="space-between" align="center" gap={12}>
            <Space>
              <Text strong>{author}</Text>
              <Tag>{message.kind}</Tag>
              {message.streamState === "streaming" && (
                <Tag color="processing">流式生成中</Tag>
              )}
              {activeToolCalls?.length ? (
                <Tag icon={<LoadingOutlined />} color="blue">
                  正在使用 {activeToolCalls.map((t) => t.toolName).join(", ")}
                </Tag>
              ) : null}
            </Space>
            <Text type="secondary" className="time">
              {formatTime(message.createdAt)}
            </Text>
          </Flex>
          {quoted && <div className="quote-block">{quoted.content}</div>}
          {showThinkingBlock && (
            <ThinkingBlock
              thinking={message.thinking ?? ""}
              expanded={expanded}
              onExpandedChange={setExpanded}
            />
          )}
          <div className="message-content">
            <MarkdownContent
              text={visibleMessageContent}
              codeRunResults={codeRunResults}
              onRunCode={!isUser ? runCodeBlock : undefined}
            />
          </div>
          <TerminalToolCards message={message} />
          {attachments.length > 0 && (
            <div
              className="message-attachments"
              data-testid="message-attachments"
            >
              {attachments.map((file) => (
                <AttachmentButton
                  key={file.file_id ?? file.id ?? attachmentName(file)}
                  file={file}
                  onOpen={openAttachment}
                />
              ))}
            </div>
          )}
          <Space>
            <Tooltip title="引用">
              <Button
                size="small"
                icon={<MessageOutlined />}
                onClick={() => onQuote?.(message)}
              />
            </Tooltip>
            <Tooltip title="复制">
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() => onCopy?.(stripInternalAgentOutput(message.content))}
              />
            </Tooltip>
            <ToolCallSummary message={message} />
          </Space>
        </div>
      </div>
      <Modal
        title={
          previewAttachment
            ? `附件预览：${attachmentName(previewAttachment)}`
            : "附件预览"
        }
        open={Boolean(previewAttachment)}
        onCancel={() => setPreviewAttachment(undefined)}
        footer={
          <Space>
            <Button
              onClick={() => setPreviewAttachment(undefined)}
              data-testid="attachment-preview-close"
            >
              关闭
            </Button>
            {previewUrl && (
              <Button href={previewUrl} target="_blank">
                打开原文件
              </Button>
            )}
          </Space>
        }
      >
        <div
          className="attachment-preview"
          data-testid="attachment-preview-modal"
        >
          {previewAttachment && (
            <Space
              direction="vertical"
              size={2}
              className="attachment-preview-meta"
            >
              <Text strong>{attachmentName(previewAttachment)}</Text>
              <Text type="secondary">
                {previewType || "未知类型"} ·{" "}
                {formatFileSize(previewAttachment.size)}
              </Text>
            </Space>
          )}
          {previewLoading ? (
            <Spin />
          ) : previewAttachment?.previewError ? (
            <Text type="danger">{previewAttachment.previewError}</Text>
          ) : previewUrl && previewType.startsWith("image/") ? (
            <>
              <img
                src={previewUrl}
                alt={
                  previewAttachment ? attachmentName(previewAttachment) : "附件"
                }
              />
              {previewAttachment?.previewText ? (
                <pre>{previewAttachment.previewText}</pre>
              ) : null}
            </>
          ) : previewAttachment?.previewText ? (
            <pre>{previewAttachment.previewText}</pre>
          ) : previewUrl && previewType.includes("pdf") ? (
            <iframe
              title={
                previewAttachment ? attachmentName(previewAttachment) : "附件"
              }
              src={previewUrl}
            />
          ) : (
            <Space direction="vertical">
              <Text strong>
                {previewAttachment && attachmentName(previewAttachment)}
              </Text>
              <Text type="secondary">
                {previewType || "未知类型"} ·{" "}
                {formatFileSize(previewAttachment?.size)}
              </Text>
              <Text type="secondary">
                后端未返回可直接渲染的内容，可以从工作区文件或原文件入口查看。
              </Text>
            </Space>
          )}
        </div>
      </Modal>
    </>
  );
}

export const MessageBubble = React.memo(
  MessageBubbleComponent,
  (prev, next) =>
    prev.message === next.message &&
    prev.version === next.version &&
    prev.workspaceId === next.workspaceId &&
    prev.currentUserAvatarUrl === next.currentUserAvatarUrl,
);

function AttachmentButton({
  file,
  onOpen,
}: {
  file: MessageAttachment;
  onOpen: (file: MessageAttachment) => void;
}) {
  const fileId = file.file_id ?? file.id;
  const image = isImageAttachment(file);
  const directUrl = file.public_url ?? file.url ?? "";
  const [thumbnailUrl, setThumbnailUrl] = useState(directUrl);
  const [thumbnailError, setThumbnailError] = useState(false);

  useEffect(() => {
    setThumbnailUrl(directUrl);
    setThumbnailError(false);
  }, [directUrl, fileId]);

  useEffect(() => {
    if (!image || directUrl || !fileId) return undefined;

    let alive = true;
    let objectUrl = "";
    api
      .previewFile(fileId)
      .then((preview) => {
        if (!preview.previewUrl) {
          if (alive) setThumbnailError(true);
          return;
        }
        if (!alive) {
          if (preview.previewUrl.startsWith("blob:")) {
            URL.revokeObjectURL(preview.previewUrl);
          }
          return;
        }
        objectUrl = preview.previewUrl;
        setThumbnailUrl(preview.previewUrl);
      })
      .catch(() => {
        if (alive) setThumbnailError(true);
      });

    return () => {
      alive = false;
      if (objectUrl.startsWith("blob:")) URL.revokeObjectURL(objectUrl);
    };
  }, [directUrl, fileId, image]);

  return (
    <button
      type="button"
      className={`message-attachment ${image ? "image" : ""}`}
      onClick={() => onOpen(file)}
      data-testid="message-attachment-preview"
    >
      {image && thumbnailUrl ? (
        <img
          className="message-attachment-thumb"
          src={thumbnailUrl}
          alt={attachmentName(file)}
        />
      ) : image ? (
        <FileImageOutlined />
      ) : (
        <CloudUploadOutlined />
      )}
      <span className="message-attachment-name">{attachmentName(file)}</span>
      <span className="message-attachment-meta">
        {formatFileSize(file.size)} · {file.parse_status ?? "stored"}
        {thumbnailError ? " · preview unavailable" : ""}
      </span>
    </button>
  );
}

function isImageAttachment(file: MessageAttachment) {
  return String(file.content_type || "").toLowerCase().startsWith("image/");
}

function codeRunsFromMessage(message: ChatMessage): Record<string, CodeRunRecord> {
  const raw = message.rawContent?.code_runs;
  if (!raw || typeof raw !== "object") return {};
  return raw as Record<string, CodeRunRecord>;
}
