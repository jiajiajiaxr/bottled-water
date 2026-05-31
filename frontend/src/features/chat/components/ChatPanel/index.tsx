import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CloudUploadOutlined,
  BulbOutlined,
  ReloadOutlined,
  SendOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Empty,
  Flex,
  Input,
  Layout,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import type { UploadProps } from "antd";
import { MessageBubble } from "@/features/chat/components/MessageBubble";
import { useMessageStore, useConversationStore } from "@/store";
import { useMessageOperations } from "@/hooks";
import { api } from "@/api";
import type { AvailableModel } from "@/api/model";
import type { ChatMessage, Conversation, UploadedFile } from "@/types";

const { Content } = Layout;
const { TextArea } = Input;
const { Text } = Typography;

export function ChatPanel({
  active,
  loading,
}: {
  active?: Conversation;
  loading: boolean;
}) {
  const [text, setText] = useState("");
  const [quoted, setQuoted] = useState<ChatMessage>();
  const [pendingFiles, setPendingFiles] = useState<UploadedFile[]>([]);
  const [selectedModelConfigId, setSelectedModelConfigId] = useState<string>();
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const { message } = AntApp.useApp();

  const {
    send,
    regenerate,
    stopStreaming,
    streamingMessages,
    streamState,
    displayOrder,
  } = useMessageOperations(currentUserName);

  // 加载可用模型列表
  useEffect(() => {
    api
      .availableModels()
      .then(setAvailableModels)
      .catch(() => {});
  }, []);

  // 从 Conversation Store 读取当前会话的思考模式状态（持久化）
  const thinkingEnabled = useConversationStore((s) =>
    active ? s.getThinkingEnabled(active.id) : false,
  );
  const setThinkingEnabled = useCallback(
    (enabled: boolean) => {
      if (active) {
        useConversationStore.getState().setThinkingEnabled(active.id, enabled);
      }
    },
    [active],
  );

  // 历史消息从 Store 读取
  const historyMessages = useMessageStore((s) => s.historyMessages);
  const messageVersions = useMessageStore((s) => s.messageVersions);

  // 合并所有消息用于 quoted 查找
  const allMessages = useMemo(
    () => [...historyMessages, ...streamingMessages.values()],
    [historyMessages, streamingMessages],
  );

  const submit = () => {
    const value =
      text.trim() || (pendingFiles.length ? "请结合上传附件继续处理。" : "");
    if (!value || !active) return;
    send(value, quoted, pendingFiles, thinkingEnabled, selectedModelConfigId);
    setText("");
    setQuoted(undefined);
    setPendingFiles([]);
  };

  const copy = useCallback(
    async (value: string) => {
      await navigator.clipboard.writeText(value);
      message.success("已复制");
    },
    [message],
  );

  // 用 Map 缓存 quoted 查找，避免每条消息渲染时都做 O(n) 遍历
  const messageById = useMemo(() => {
    const map = new Map<string, ChatMessage>();
    for (const item of allMessages) {
      map.set(item.id, item);
    }
    return map;
  }, [allMessages]);

  const handleQuote = useCallback((msg: ChatMessage) => setQuoted(msg), []);
  const handleRegenerate = useCallback(
    (msg: ChatMessage) => regenerate(msg),
    [regenerate],
  );
  const handleCopy = useCallback((value: string) => copy(value), [copy]);
  const handlePreview = useCallback(
    (msg: ChatMessage) => onOpenPreview(msg),
    [onOpenPreview],
  );

  const messageListRef = useRef<HTMLDivElement>(null);
  const isAtBottom = useRef(true);

  const uploadProps: UploadProps = {
    showUploadList: false,
    customRequest: async (options) => {
      const uploaded = await onUploadFile(options.file as File);
      setPendingFiles((current) => [uploaded, ...current]);
      options.onSuccess?.("ok");
    },
  };

  useEffect(() => {
    const el = messageListRef.current;
    if (!el) return;

    const handleScroll = () => {
      const threshold = 50;
      isAtBottom.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!isAtBottom.current) return;
    const el = messageListRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [historyMessages, displayOrder, streamState]);

  const renderMessageBubble = (item: ChatMessage) => {
    return (
      <MessageBubble
        key={item.id}
        message={item}
        version={messageVersions.get(item.id) ?? 0}
        quoted={
          item.quotedMessageId
            ? messageById.get(item.quotedMessageId)
            : undefined
        }
        onQuote={handleQuote}
        onRegenerate={handleRegenerate}
        onCopy={handleCopy}
        onPreview={handlePreview}
      />
    );
  };

  return (
    <Content className="chat-panel">
      <div ref={messageListRef} className="message-list">
        {loading ? (
          <Spin />
        ) : allMessages.length ? (
          <>
            {historyMessages.map(renderMessageBubble)}
            {displayOrder.map((agentId) => {
              const msg = streamingMessages.get(agentId);

              console.log(msg);

              return msg ? renderMessageBubble(msg) : null;
            })}
          </>
        ) : (
          <Empty description="暂无消息" />
        )}
      </div>
      <div className="composer">
        {quoted && (
          <div className="composer-quote">
            <div className="composer-quote-text">
              <Text type="secondary">引用：{quoted.content}</Text>
            </div>
            <Button
              type="text"
              size="small"
              onClick={() => setQuoted(undefined)}
            >
              取消
            </Button>
          </div>
        )}
        {pendingFiles.length > 0 && (
          <div className="composer-files" data-testid="composer-attachments">
            {pendingFiles.map((file) => (
              <Tag
                key={file.id}
                closable
                icon={<CloudUploadOutlined />}
                onClose={() =>
                  setPendingFiles((current) =>
                    current.filter((item) => item.id !== file.id),
                  )
                }
              >
                {file.original_filename} · {Math.ceil(file.size / 1024)}KB ·{" "}
                {file.parse_status}
              </Tag>
            ))}
          </div>
        )}
        <TextArea
          data-testid="message-input"
          aria-label="message-input"
          autoSize={{ minRows: 2, maxRows: 6 }}
          value={text}
          placeholder="输入消息，支持 @Agent 指定响应；Enter 发送，Shift+Enter 换行"
          onChange={(event) => setText(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <Flex justify="space-between" align="center">
          <Space>
            <Upload {...uploadProps}>
              <Button icon={<CloudUploadOutlined />} data-testid="file-upload">
                上传文件
              </Button>
            </Upload>
          </Space>
          <Space>
            <Tooltip title={thinkingEnabled ? "已开启思考模式" : "思考模式"}>
              <Button
                type={thinkingEnabled ? "primary" : "default"}
                ghost={thinkingEnabled}
                icon={<BulbOutlined />}
                onClick={() => setThinkingEnabled(!thinkingEnabled)}
                disabled={!active}
                data-testid="thinking-toggle"
              >
                思考
              </Button>
            </Tooltip>
            <Select
              placeholder="选择模型"
              value={selectedModelConfigId}
              onChange={setSelectedModelConfigId}
              allowClear
              style={{ minWidth: 160 }}
              options={availableModels.map((m) => ({
                value: m.config_id,
                label: `${m.name} (${m.model_id})`,
              }))}
              onClear={() => setSelectedModelConfigId(undefined)}
              disabled={!active}
            />
            <Tooltip title="刷新模型列表">
              <Button
                icon={<SyncOutlined />}
                onClick={() =>
                  api
                    .availableModels(true)
                    .then(setAvailableModels)
                    .catch(() => {})
                }
                disabled={!active}
              />
            </Tooltip>
            {streamState === "streaming" ? (
              <Button danger icon={<ReloadOutlined />} onClick={stopStreaming}>
                Stop
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SendOutlined />}
                onClick={submit}
                disabled={!active}
                data-testid="send-message"
              >
                发送
              </Button>
            )}
          </Space>
        </Flex>
      </div>
    </Content>
  );
}
