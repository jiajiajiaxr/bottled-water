import { useState } from "react";
import {
  Avatar,
  Button,
  Divider,
  Drawer,
  List,
  Select,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
  Modal,
} from "antd";
import { DeleteOutlined } from "@ant-design/icons";
import { participantName } from "@/lib/message";
import type { Agent, Conversation } from "@/types";

const { Text } = Typography;

export function MembersDrawer({
  open,
  active,
  agents,
  onClose,
  onAddAgents,
  onRemoveParticipant,
}: {
  open: boolean;
  active?: Conversation;
  agents: Agent[];
  onClose: () => void;
  onAddAgents: (ids: string[]) => void;
  onRemoveParticipant: (
    participant: Conversation["participants"][number],
  ) => Promise<void>;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const isGroup = active?.chat_type === "group";
  const existing = new Set(
    active?.participants.map((item) => item.agent_id).filter(Boolean),
  );
  const removableAgentCount =
    active?.participants.filter((item) => item.participant_type === "agent")
      .length ?? 0;
  const options = agents
    .filter((agent) => !existing.has(agent.id) && agent.status === "online")
    .map((agent) => ({
      label: `${agent.name} · ${agent.type}`,
      value: agent.id,
    }));

  return (
    <Drawer title="群聊成员与邀请" width={460} open={open} onClose={onClose}>
      <Statistic
        title="当前 Agent 人数"
        value={active?.agent_count ?? active?.participants.length ?? 0}
        suffix="/8"
      />
      <List
        className="member-list"
        dataSource={active?.participants ?? []}
        renderItem={(item) => (
          <List.Item
            actions={[
              item.participant_type === "agent" && removableAgentCount <= 1 ? (
                <Tooltip key="last-agent" title="至少保留 1 个 Agent">
                  <Button
                    size="small"
                    shape="circle"
                    icon={<DeleteOutlined />}
                    disabled
                  />
                </Tooltip>
              ) : (
                <Tooltip key="remove" title="移除成员">
                  <Button
                    size="small"
                    danger
                    shape="circle"
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      Modal.confirm({
                        title: `移除成员：${participantName(item)}`,
                        content:
                          "移除后该 Agent 不再参与当前群聊，默认工作流也会同步刷新。",
                        okText: "移除",
                        okButtonProps: { danger: true },
                        onOk: () => onRemoveParticipant(item),
                      });
                    }}
                  />
                </Tooltip>
              ),
            ]}
          >
            <List.Item.Meta
              avatar={<Avatar>{participantName(item).slice(0, 1)}</Avatar>}
              title={
                <Space>
                  <Text strong>{participantName(item)}</Text>
                  <Tag>{item.role ?? "member"}</Tag>
                </Space>
              }
              description={`${item.participant_type ?? "agent"} · ${item.agent_status ?? "active"}`}
            />
          </List.Item>
        )}
      />
      <Divider />
      {isGroup ? (
        <>
          <Text strong>邀请 Agent 加入</Text>
          <Select
            mode="multiple"
            className="full-width mt-8"
            options={options}
            value={selected}
            onChange={setSelected}
            placeholder="选择要加入的 Agent"
          />
          <Button
            className="mt-8"
            type="primary"
            disabled={!selected.length}
            onClick={() => {
              onAddAgents(selected);
              setSelected([]);
            }}
          >
            加入群聊
          </Button>
        </>
      ) : (
        <Text type="secondary">
          单聊只保留一个 Agent；需要多人协作时请创建多 Agent 群聊。
        </Text>
      )}
    </Drawer>
  );
}
