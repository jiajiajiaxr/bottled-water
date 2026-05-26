import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  BranchesOutlined,
  CloudUploadOutlined,
  BulbOutlined,
  ReloadOutlined,
  SendOutlined,
  SettingOutlined,
  UserAddOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Avatar,
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
import type { UploadProps } from "antd";
import { participantName } from "../../../../lib/message";
import { MessageBubble } from "../MessageBubble";
import type {
  ChatMessage,
  Conversation,
  UploadedFile,
  User,
} from "../../../../types";

const { Content, Header } = Layout;
const { TextArea } = Input;
const { Title, Text } = Typography;
type UploadRequestOption = Parameters<NonNullable<UploadProps["customRequest"]>>[0];

export function ChatPanel({
  user,
  active,
  messages,
  loading,
  streamState,
  onSend,
  onRegenerate,
  onOpenMembers,
  onOpenSettings,
  onOpenWorkflow,
  workflowMode = false,
  workflowContent,
  onUploadFile,
  onOpenPreview,
  onStopStreaming,
}: {
  user: User;
  active?: Conversation;
  messages: ChatMessage[];
  loading: boolean;
  streamState: "idle" | "streaming" | "done" | "error";
  onSend: (
    text: string,
    quoted?: ChatMessage,
    attachments?: UploadedFile[],
    thinkingEnabled?: boolean,
  ) => void;
  onRegenerate: (message: ChatMessage) => void;
  onOpenMembers: () => void;
  onOpenSettings: () => void;
  onOpenWorkflow: () => void;
  workflowMode?: boolean;
  workflowContent?: ReactNode;
  onUploadFile: (file: File) => Promise<UploadedFile>;
  onOpenPreview: (message: ChatMessage) => void;
  onStopStreaming: () => void;
}) {
  const [text, setText] = useState("");
  const [quoted, setQuoted] = useState<ChatMessage>();
  const [pendingFiles, setPendingFiles] = useState<UploadedFile[]>([]);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const { message } = AntApp.useApp();

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

  const participantAvatars = active?.participants.slice(0, 8) ?? [];

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
    <Content className={`chat-panel${workflowMode ? " workflow-mode" : ""}`}>
      <Header className="chat-header">
        <div>
          <Space align="center" wrap>
            <Title level={3}>{active?.title ?? "选择会话"}</Title>
            {active?.chat_type === "group" && (
              <Tag color="blue">
                {active.agent_count ?? active.participants.length}/8 Agent
              </Tag>
            )}
            {active?.master_enabled && <Tag color="green">主控调度</Tag>}
          </Space>
          <Space size={4} wrap className="participant-strip">
            {participantAvatars.map((item) => (
              <Tooltip
                title={`${participantName(item)} · ${item.role ?? "member"}`}
                key={item.id ?? item.agent_id}
              >
                <Avatar
                  size="small"
                  style={{
                    background:
                      item.agent_status === "offline" ? "#9ca3af" : "#1677ff",
                  }}
                >
                  {participantName(item).slice(0, 1)}
                </Avatar>
              </Tooltip>
            ))}
            {active?.chat_type === "group" && (
              <>
                <Button
                  size="small"
                  icon={<UserAddOutlined />}
                  onClick={onOpenMembers}
                  data-testid="conversation-members"
                >
                  成员
                </Button>
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  onClick={onOpenWorkflow}
                  data-testid="conversation-workflow"
                >
                  工作流画布
                </Button>
                <Button
                  size="small"
                  icon={<SettingOutlined />}
                  onClick={onOpenSettings}
                  data-testid="conversation-settings"
                >
                  群聊设置
                </Button>
              </>
            )}
          </Space>
        </div>
        <Space>
          {streamState === "streaming" && <Spin size="small" />}
          <Avatar>{user.avatar ?? user.name.slice(0, 1)}</Avatar>
        </Space>
      </Header>
      {workflowMode && workflowContent ? (
        <div className="workflow-chat-host">{workflowContent}</div>
      ) : (
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
      )}
      {!workflowMode && (
      <div className="composer">
        {quoted && (
          <div className="composer-quote">
            <Text type="secondary" ellipsis>
              引用：{quoted.content}
            </Text>
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
              <Button danger icon={<ReloadOutlined />} onClick={onStopStreaming}>
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
      )}
    </Content>
  );
}
