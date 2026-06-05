import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CloudUploadOutlined,
  BulbOutlined,
  SendOutlined,
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
import { api } from "@/api";
import { MessageBubble } from "@/features/chat/components/MessageBubble";
import { RuntimeDecisionStrip } from "@/features/chat/components/ChatPanel/RuntimeDecisionStrip";
import { useMessageStore, useConversationStore } from "@/store";
import { useMessageOperations } from "@/hooks";
import type { ChatMessage, Conversation, ModelConfig, UploadedFile } from "@/types";

const { Content } = Layout;
const { TextArea } = Input;
const { Text } = Typography;
const AGENT_MODEL_SENTINEL = "__agent_model__";

export function ChatPanel({
  active,
  loading,
  userName,
  defaultModelConfigId,
  onPreviewArtifact,
}: {
  active?: Conversation;
  loading: boolean;
  userName?: string;
  defaultModelConfigId?: string;
  onPreviewArtifact?: (message: ChatMessage) => void;
}) {
  const [text, setText] = useState("");
  const [quoted, setQuoted] = useState<ChatMessage>();
  const [pendingFiles, setPendingFiles] = useState<UploadedFile[]>([]);
  const [awaitingResponse, setAwaitingResponse] = useState(false);
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const { message } = AntApp.useApp();
  const { send, streamingMessages, displayOrder } = useMessageOperations(userName);

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
  const selectedModelConfigId = useConversationStore((s) =>
    active ? s.getSelectedModelConfigId(active.id) : undefined,
  );
  const setSelectedModelConfigId = useCallback(
    (value: string) => {
      if (active) {
        useConversationStore.getState().setSelectedModelConfigId(active.id, value);
      }
    },
    [active],
  );

  useEffect(() => {
    if (!active?.id) return;
    const snippet = useConversationStore.getState().consumeDraftSnippet(active.id);
    if (!snippet) return;
    setText((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}${snippet}`);
  }, [active?.id]);

  // 历史消息从 Store 读取
  const historyMessages = useMessageStore((s) => s.historyMessages);
  const messageVersions = useMessageStore((s) => s.messageVersions);

  // 合并所有消息用于 quoted 查找
  const allMessages = useMemo(
    () => [...historyMessages, ...streamingMessages.values()],
    [historyMessages, streamingMessages],
  );
  const chatDefaultModelConfigId =
    defaultModelConfigId ||
    modelConfigs.find((item) => item.status === "active")?.id ||
    modelConfigs[0]?.id;
  const chatModelSelectValue =
    selectedModelConfigId || chatDefaultModelConfigId || AGENT_MODEL_SENTINEL;
  const runtimeModelConfigId =
    chatModelSelectValue === AGENT_MODEL_SENTINEL ? undefined : chatModelSelectValue;
  const modelOptions = useMemo(
    () => [
      ...modelConfigs.map((item) => ({
        label: `${item.name || item.model_id} · ${item.provider_name || item.model_id}`,
        value: item.id,
      })),
      {
        label: "跟随 Agent 绑定模型",
        value: AGENT_MODEL_SENTINEL,
      },
    ],
    [modelConfigs],
  );

  const submit = () => {
    const value =
      text.trim() || (pendingFiles.length ? "请结合上传附件继续处理。" : "");
    if (!value || !active) return;
    setAwaitingResponse(true);
    send(value, quoted, pendingFiles, thinkingEnabled, runtimeModelConfigId);
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
  const handleCopy = useCallback((value: string) => copy(value), [copy]);
  const messageListRef = useRef<HTMLDivElement>(null);
  const isAtBottom = useRef(true);

  const uploadProps: UploadProps = {};

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
  }, [historyMessages, displayOrder]);

  // 进入新对话且消息加载完成后，滚动到底部
  useEffect(() => {
    if (!active?.id || loading) return;
    isAtBottom.current = true;
    const el = messageListRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [active?.id, loading]);

  useEffect(() => {
    let alive = true;
    api.modelConfigs()
      .then((items) => {
        if (alive) {
          setModelConfigs(items);
        }
      })
      .catch(() => {
        if (alive) {
          setModelConfigs([]);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  // 智能体开始回复后，隐藏思考中指示器
  useEffect(() => {
    if (awaitingResponse && (streamingMessages.size > 0 || displayOrder.length > 0)) {
      setAwaitingResponse(false);
    }
  }, [streamingMessages.size, displayOrder.length, awaitingResponse]);

  const renderMessageBubble = (item: ChatMessage) => {
    return (
      <MessageBubble
        key={item.id}
        message={item}
        workspaceId={active?.workspace_id}
        version={messageVersions.get(item.id) ?? 0}
        quoted={
          item.quotedMessageId
            ? messageById.get(item.quotedMessageId)
            : undefined
        }
        onQuote={handleQuote}
        onCopy={handleCopy}
        onPreview={(message) => onPreviewArtifact?.(message)}
      />
    );
  };

  return (
    <Content className="chat-panel">
      <div ref={messageListRef} className="message-list">
        <RuntimeDecisionStrip conversation={active} />
        {loading ? (
          <Spin />
        ) : allMessages.length ? (
          <>
            {historyMessages.map(renderMessageBubble)}
            {displayOrder.map((agentId) => {
              const msg = streamingMessages.get(agentId);

              return msg ? renderMessageBubble(msg) : null;
            })}
            {awaitingResponse && (
              <div className="thinking-indicator">
                <div className="thinking-indicator-dots">
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                </div>
                <span className="thinking-indicator-text">思考中</span>
              </div>
            )}
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
            <Select
              className="composer-model-select"
              size="middle"
              value={chatModelSelectValue}
              options={modelOptions}
              onChange={setSelectedModelConfigId}
              disabled={!active || modelOptions.length === 0}
              popupMatchSelectWidth={280}
              data-testid="composer-model-select"
            />
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
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={submit}
              disabled={!active}
              data-testid="send-message"
            >
              发送
            </Button>
          </Space>
        </Flex>
      </div>
    </Content>
  );
}
