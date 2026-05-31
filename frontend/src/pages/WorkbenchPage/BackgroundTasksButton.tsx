import { useMemo, useState } from "react";
import {
  Badge,
  Button,
  Divider,
  Flex,
  Input,
  List,
  Popover,
  Progress,
  Space,
  Tag,
  Typography,
} from "antd";
import { ApiOutlined } from "@ant-design/icons";
import { isTaskRunning } from "@/lib/message";
import { formatTime } from "@/lib/format";
import { useMessageOperations } from "@/hooks";
import type { AgentTask, Conversation } from "@/types";

const { Text, Title } = Typography;
const { TextArea } = Input;

export function BackgroundTasksButton({
  tasks,
  conversations,
  activeConversationId,
  currentUserName,
  onOpenConversation,
  onAfterSend,
  onCancel,
  onRefresh,
}: {
  tasks: AgentTask[];
  conversations: Conversation[];
  activeConversationId?: string;
  currentUserName: string;
  onOpenConversation: (conversationId: string) => void;
  onAfterSend: () => Promise<void>;
  onCancel: (task: AgentTask) => Promise<void>;
  onRefresh: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const { send } = useMessageOperations();
  const conversationMap = useMemo(
    () => new Map(conversations.map((item) => [item.id, item.title])),
    [conversations],
  );
  const running = tasks.filter((task) => isTaskRunning(task.status));
  const recent = tasks.slice(0, 8);

  const create = async () => {
    const value = draft.trim();
    if (!value || !activeConversationId) return;
    setCreating(true);
    try {
      await send(value);
      await onAfterSend();
      setDraft("");
      setOpen(false);
    } finally {
      setCreating(false);
    }
  };

  const content = (
    <div
      className="background-task-popover"
      data-testid="background-task-popover"
    >
      <Flex
        justify="space-between"
        align="center"
        className="background-task-head"
      >
        <Text type="secondary">后台任务</Text>
        <Text type="secondary">进行 {running.length}</Text>
      </Flex>
      {recent.length ? (
        <List
          className="background-task-list"
          dataSource={recent}
          renderItem={(task) => (
            <List.Item
              actions={
                isTaskRunning(task.status)
                  ? [
                      <Button
                        key="cancel"
                        size="small"
                        danger
                        onClick={(event) => {
                          event.stopPropagation();
                          onCancel(task);
                        }}
                      >
                        停止
                      </Button>,
                    ]
                  : []
              }
            >
              <button
                type="button"
                className="background-task-item"
                onClick={() =>
                  task.conversation_id &&
                  onOpenConversation(task.conversation_id)
                }
              >
                <Flex justify="space-between" gap={10} align="center">
                  <Text strong ellipsis>
                    {task.title}
                  </Text>
                  <Tag
                    color={
                      isTaskRunning(task.status)
                        ? "processing"
                        : task.status === "COMPLETED"
                          ? "success"
                          : "default"
                    }
                  >
                    {task.status}
                  </Tag>
                </Flex>
                <Progress
                  percent={Math.min(100, task.progress ?? 0)}
                  size="small"
                  showInfo={false}
                />
                <Text type="secondary" ellipsis>
                  {task.conversation_id
                    ? (conversationMap.get(task.conversation_id) ?? "关联会话")
                    : "独立任务"}{" "}
                  · {formatTime(task.updated_at ?? task.created_at)}
                </Text>
              </button>
            </List.Item>
          )}
        />
      ) : (
        <div className="background-task-empty">
          <div className="background-task-empty-icon">
            <ApiOutlined />
          </div>
          <Title level={4}>暂无生成中内容</Title>
          <Text type="secondary">可以随时对话，让 AI 为你生成哦</Text>
        </div>
      )}
      <Divider />
      <Space direction="vertical" className="full-width" size={8}>
        <TextArea
          rows={3}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="输入要放到当前会话后台执行的任务"
          data-testid="background-task-input"
        />
        <Flex justify="space-between" gap={8}>
          <Button onClick={onRefresh}>刷新</Button>
          <Button
            type="primary"
            loading={creating}
            disabled={!draft.trim() || !activeConversationId}
            onClick={create}
          >
            创建后台任务
          </Button>
        </Flex>
      </Space>
    </div>
  );

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottomRight"
      content={content}
    >
      <Badge count={running.length} size="small">
        <Button icon={<ApiOutlined />} data-testid="background-tasks">
          后台任务
        </Button>
      </Badge>
    </Popover>
  );
}
