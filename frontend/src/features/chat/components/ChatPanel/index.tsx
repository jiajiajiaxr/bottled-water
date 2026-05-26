import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CloudUploadOutlined,
  BulbOutlined,
  ReloadOutlined,
  SendOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Empty,
  Flex,
  Input,
  Layout,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
// rc-upload 类型声明缺失，使用 any 绕过
type UploadRequestOption = any;
import { MessageBubble } from "@/features/chat/components/MessageBubble";
import { useMessageStore } from "@/store";
import type {
  ChatMessage,
  Conversation,
  UploadedFile,
} from "@/types";

const { Content } = Layout;
const { TextArea } = Input;
const { Text } = Typography;

export function ChatPanel({
  active,
  loading,
  streamState,
  onSend,
  onRegenerate,
  onUploadFile,
  onOpenPreview,
  onStopStreaming,
}: {
  active?: Conversation;
  loading: boolean;
  streamState: "idle" | "streaming" | "done" | "error";
  onSend: (
    text: string,
    quoted?: ChatMessage,
    attachments?: UploadedFile[],
    thinkingEnabled?: boolean,
  ) => void;
  onRegenerate: (message: ChatMessage) => void;
  onUploadFile: (file: File) => Promise<UploadedFile>;
  onOpenPreview: (message: ChatMessage) => void;
  onStopStreaming: () => void;
}) {
  const [text, setText] = useState("");
  const [quoted, setQuoted] = useState<ChatMessage>();
  const [pendingFiles, setPendingFiles] = useState<UploadedFile[]>([]);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const { message } = AntApp.useApp();

  // 从 Store 分别订阅历史消息和流式消息，互不影响
  const historyMessages = useMessageStore((s) => s.historyMessages);
  const streamingMessages = useMessageStore((s) => s.streamingMessages);

  // 合并为渲染列表（保持按时间顺序）
  const messages = useMemo(() => {
    const streaming = Array.from(streamingMessages.values());
    const merged = [...historyMessages, ...streaming].sort(
      (a, b) =>
        new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    );
    return merged;
  }, [historyMessages, streamingMessages]);

  const submit = () => {
    const value =
      text.trim() || (pendingFiles.length ? "请结合上传附件继续处理。" : "");
    if (!value || !active) return;
    onSend(value, quoted, pendingFiles, thinkingEnabled);
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
    for (const item of messages) {
      map.set(item.id, item);
    }
    return map;
  }, [messages]);

  const handleQuote = useCallback((msg: ChatMessage) => setQuoted(msg), []);
  const handleRegenerate = useCallback(
    (msg: ChatMessage) => onRegenerate(msg),
    [onRegenerate],
  );
  const handleCopy = useCallback((value: string) => copy(value), [copy]);
  const handlePreview = useCallback(
    (msg: ChatMessage) => onOpenPreview(msg),
    [onOpenPreview],
  );

  const messageListRef = useRef<HTMLDivElement>(null);
  const isAtBottom = useRef(true);

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
  }, [messages, streamState]);

  return (
    <Content className="chat-panel">
      <div ref={messageListRef} className="message-list">
        {loading ? (
          <Spin />
        ) : messages.length ? (
          messages.map((item) => (
            <MessageBubble
              key={item.id}
              message={item}
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
          ))
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
            <Upload
              showUploadList={false}
              customRequest={async (options: UploadRequestOption) => {
                const uploaded = await onUploadFile(options.file as File);
                setPendingFiles((current) => [uploaded, ...current]);
                options.onSuccess?.("ok");
              }}
            >
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
                onClick={() => setThinkingEnabled((v) => !v)}
                disabled={!active}
                data-testid="thinking-toggle"
              >
                思考
              </Button>
            </Tooltip>
            {streamState === "streaming" ? (
              <Button
                danger
                icon={<ReloadOutlined />}
                onClick={onStopStreaming}
              >
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
