import { useEffect, useRef } from "react";
import { Checkbox, Form, Input, Modal, Select } from "antd";
import { normalizeConversationCategory } from "@/lib/conversation";
import type { Agent } from "@/types";

const COPY = {
  createChat: "\u521b\u5efa\u804a\u5929",
  conversationName: "\u4f1a\u8bdd\u540d\u79f0",
  groupPlaceholder: "\u591a Agent \u534f\u4f5c\u4f1a\u8bdd",
  singlePlaceholder: "\u5355\u804a\u4f1a\u8bdd",
  folder: "\u5206\u7c7b/\u6587\u4ef6\u5939",
  folderPlaceholder: "\u9009\u62e9\u5de6\u4fa7\u5206\u7c7b",
  chooseGroupAgent: "\u9009\u62e9 1-8 \u4e2a Agent",
  chooseSingleAgent: "\u9009\u62e9 1 \u4e2a Agent",
  groupAgentRequired: "\u9700\u8981\u9009\u62e9 1-8 \u4e2a Agent",
  singleAgentRequired: "\u5355\u804a\u9700\u8981\u9009\u62e9 1 \u4e2a Agent",
  agentPlaceholder: "\u4ece Agent \u901a\u8baf\u5f55\u9009\u62e9",
  autoOrganize: "\u81ea\u52a8\u7ec4\u7ec7\u591a Agent \u534f\u4f5c",
  dailyChat: "\u65e5\u5e38\u804a\u5929",
};

export function CreateConversationModal({
  open,
  group = true,
  agents,
  categoryOptions,
  onCancel,
  onCreate,
}: {
  open: boolean;
  group?: boolean;
  agents: Agent[];
  categoryOptions: string[];
  onCancel: () => void;
  onCreate: (payload: {
    title?: string;
    agentIds: string[];
    group?: boolean;
    masterEnabled: boolean;
    folder: string;
  }) => void;
}) {
  const [form] = Form.useForm();
  const onlineAgents = agents.filter((agent) => agent.status === "online");
  const maxAgentCount = group ? 8 : 1;
  const initializedRef = useRef(false);
  const selectedAgentIdsRef = useRef<string[]>([]);
  const categorySelectOptions = categoryOptions.map((name) => ({
    label: name,
    value: name,
  }));

  const setSelectedAgentIds = (ids: string[]) => {
    const next = group ? ids.slice(0, maxAgentCount) : ids.slice(0, 1);
    selectedAgentIdsRef.current = next;
    form.setFieldValue("agentIds", next);
  };

  useEffect(() => {
    if (!open) {
      initializedRef.current = false;
      selectedAgentIdsRef.current = [];
      form.resetFields();
      return;
    }
    if (initializedRef.current) return;
    if (onlineAgents.length === 0) return;
    initializedRef.current = true;

    const defaultAgentIds = pickDefaultAgentIds(onlineAgents, maxAgentCount);
    selectedAgentIdsRef.current = defaultAgentIds;
    form.setFieldsValue({
      agentIds: defaultAgentIds,
      masterEnabled: group,
      folder: "Default",
    });
  }, [open, onlineAgents, form, group, maxAgentCount]);

  const submit = async () => {
    const latestAgentIds =
      selectedAgentIdsRef.current.length > 0
        ? selectedAgentIdsRef.current
        : form.getFieldValue("agentIds") || [];
    form.setFieldValue("agentIds", latestAgentIds);
    const values = await form.validateFields();
    onCreate({
      title: values.title,
      agentIds: latestAgentIds,
      group,
      masterEnabled: values.masterEnabled ?? group,
      folder: normalizeConversationCategory(values.folder),
    });
    selectedAgentIdsRef.current = [];
    form.resetFields();
  };

  return (
    <Modal
      title={COPY.createChat}
      open={open}
      onCancel={onCancel}
      onOk={submit}
      okText={COPY.createChat}
      okButtonProps={{ "data-testid": "create-conversation-confirm" }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ masterEnabled: group, folder: "Default" }}
      >
        <Form.Item name="title" label={COPY.conversationName}>
          <Input placeholder={group ? COPY.groupPlaceholder : COPY.singlePlaceholder} />
        </Form.Item>
        <Form.Item name="folder" label={COPY.folder}>
          <Select options={categorySelectOptions} placeholder={COPY.folderPlaceholder} />
        </Form.Item>
        <Form.Item
          name="agentIds"
          label={group ? COPY.chooseGroupAgent : COPY.chooseSingleAgent}
          rules={[
            {
              validator: async (_, value?: string[]) => {
                const count = value?.length ?? 0;
                if (group && (count < 1 || count > maxAgentCount)) {
                  throw new Error(COPY.groupAgentRequired);
                }
                if (!group && count !== 1) {
                  throw new Error(COPY.singleAgentRequired);
                }
              },
            },
          ]}
        >
          <Select
            data-testid="agent-select"
            mode="multiple"
            maxCount={maxAgentCount}
            placeholder={COPY.agentPlaceholder}
            onChange={(value) => setSelectedAgentIds(value)}
            onSelect={(_, option) => {
              if (!group) setSelectedAgentIds([String(option.value)]);
            }}
            options={onlineAgents.map((agent) => ({
              label: `${agent.name} \u00b7 ${agent.capabilities
                .slice(0, 2)
                .map((cap) => cap.label)
                .join("/")}`,
              value: agent.id,
            }))}
          />
        </Form.Item>
        {group && (
          <Form.Item name="masterEnabled" valuePropName="checked">
            <Checkbox>{COPY.autoOrganize}</Checkbox>
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}

function pickDefaultAgentIds(agents: Agent[], maxAgentCount: number): string[] {
  const dailyAgent = agents.find((agent) => {
    const lowerName = agent.name.toLowerCase();
    return lowerName.includes("daily chat") || agent.name.includes(COPY.dailyChat);
  });
  const fallback = dailyAgent ?? agents[0];
  return fallback ? [fallback.id].slice(0, maxAgentCount) : [];
}
