import React, { useEffect, useState } from "react";
import {
  BranchesOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  EyeOutlined,
  LoadingOutlined,
  MessageOutlined,
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
import { formatFileSize } from "@/lib/format";
import { MarkdownContent } from "@/lib/markdown";
import {
  attachmentName,
  messageAttachments,
  stripInternalAgentOutput,
} from "@/lib/message";
import { formatTime } from "@/lib/format";
import { useConversationStore } from "@/store";
import type { ChatMessage, MessageAttachment } from "@/types";
import ThinkingBlock from "./ThinkingBlock";

const { Text, Paragraph } = Typography;

interface MessageBubbleProps {
  message: ChatMessage;
  version: number;
  quoted?: ChatMessage;
  onQuote: (message: ChatMessage) => void;
  onCopy: (text: string) => void;
  onPreview: (message: ChatMessage) => void;
}

function MessageBubbleComponent({
  message,
  version: _version,
  quoted,
  onQuote,
  onCopy,
  onPreview,
}: MessageBubbleProps) {
  const author = message.author || "未知";
  const isUser = message.role === "user";
  const isEvent =
    message.kind === "event" ||
    message.role === "system" ||
    message.role === "tool";
  const thinkingEnabled = useConversationStore((s) =>
    s.getThinkingEnabled(message.conversationId),
  );
  const attachments = messageAttachments(message);
  const [previewAttachment, setPreviewAttachment] = useState<
    | (MessageAttachment & {
        previewUrl?: string;
        previewText?: string;
        contentType?: string;
        previewError?: string;
      })
    | undefined
  >();
  const [previewLoading, setPreviewLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const onExpandedChange = (expanded: boolean) => setExpanded(expanded);

  useEffect(() => {
    return () => {
      if (previewAttachment?.previewUrl?.startsWith("blob:"))
        URL.revokeObjectURL(previewAttachment.previewUrl);
    };
  }, [previewAttachment?.previewUrl]);

  const openAttachment = async (attachment: MessageAttachment) => {
    const next = {
      ...attachment,
      contentType: attachment.content_type,
      previewText: attachment.extracted_text,
      previewUrl: attachment.public_url ?? attachment.url,
    };
    setPreviewAttachment(next);
    const fileId = attachment.file_id ?? attachment.id;
    if (
      !fileId ||
      attachment.extracted_text ||
      attachment.public_url ||
      attachment.url
    )
      return;
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
        <Avatar className="message-avatar">{author.slice(0, 1)}</Avatar>
        <button
          className="message-card preview-message-card preview-card-button"
          data-testid="preview-card"
          onClick={() => onPreview(message)}
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

  return (
    <>
      <div className={`message-row ${isUser ? "from-user" : "from-agent"}`}>
        <Avatar className="message-avatar">{author.slice(0, 1)}</Avatar>
        <div className="message-card">
          <Flex justify="space-between" align="center" gap={12}>
            <Space>
              <Text strong>{author}</Text>
              <Tag>{message.kind}</Tag>
              {message.streamState === "streaming" && (
                <Tag color="processing">流式生成中</Tag>
              )}
              {(
                message.rawContent?._activeToolCalls as
                  | Array<{ toolName: string }>
                  | undefined
              )?.length ? (
                <Tag icon={<LoadingOutlined />} color="blue">
                  正在使用{" "}
                  {(
                    message.rawContent?._activeToolCalls as Array<{
                      toolName: string;
                    }>
                  )
                    .map((t) => t.toolName)
                    .join(", ")}
                </Tag>
              ) : null}
            </Space>
            <Text type="secondary" className="time">
              {formatTime(message.createdAt)}
            </Text>
          </Flex>
          {quoted && <div className="quote-block">{quoted.content}</div>}
          {thinkingEnabled && !isUser && (
            <ThinkingBlock
              thinking={message.thinking ?? ""}
              expanded={expanded}
              onExpandedChange={onExpandedChange}
            />
          )}
          <div className="message-content">
            {message.streamState === "streaming" ? (
              <div className="markdown-content">{message.content}</div>
            ) : (
              <MarkdownContent text={message.content} />
            )}
          </div>
          {attachments.length > 0 && (
            <div
              className="message-attachments"
              data-testid="message-attachments"
            >
              {attachments.map((file) => (
                <button
                  type="button"
                  key={file.file_id ?? file.id ?? attachmentName(file)}
                  className="message-attachment"
                  onClick={() => openAttachment(file)}
                  data-testid="message-attachment-preview"
                >
                  <CloudUploadOutlined />
                  <span className="message-attachment-name">
                    {attachmentName(file)}
                  </span>
                  <span className="message-attachment-meta">
                    {formatFileSize(file.size)} ·{" "}
                    {file.parse_status ?? "stored"}
                  </span>
                </button>
              ))}
            </div>
          )}
          <Space>
            <Tooltip title="引用">
              <Button
                size="small"
                icon={<MessageOutlined />}
                onClick={() => onQuote(message)}
              />
            </Tooltip>
            <Tooltip title="复制">
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() =>
                  onCopy(stripInternalAgentOutput(message.content))
                }
              />
            </Tooltip>
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
          ) : previewAttachment?.previewText ? (
            <pre>{previewAttachment.previewText}</pre>
          ) : previewUrl && previewType.startsWith("image/") ? (
            <img
              src={previewUrl}
              alt={
                previewAttachment ? attachmentName(previewAttachment) : "附件"
              }
            />
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
                后端未返回可直接渲染的内容，可从文件资产或原文件入口查看。
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
  (prev, next) => {
    return prev.version === next.version;
  },
);
