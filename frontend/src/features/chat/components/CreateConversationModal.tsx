import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Checkbox, Form, Input, Modal, Select } from "antd";
import { normalizeConversationCategory } from "../../../lib/conversation";
import type { Agent } from "../../../types";

function normalizeAgentIds(value: unknown, group: boolean): string[] {
  const items = Array.isArray(value) ? value : value ? [value] : [];
  const ids = Array.from(new Set(items.map(String).filter(Boolean)));
  return group ? ids.slice(0, 8) : ids.slice(0, 1);
}

export function CreateConversationModal({
  open,
  group,
  agents,
  categoryOptions,
  onCancel,
  onCreate,
}: {
  open: boolean;
  group: boolean;
  agents: Agent[];
  categoryOptions: string[];
  onCancel: () => void;
  onCreate: (payload: {
    title?: string;
    agentIds: string[];
    group: boolean;
    masterEnabled: boolean;
    folder: string;
  }) => void;
}) {
  const [form] = Form.useForm();
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const selectedAgentIdsRef = useRef<string[]>([]);
  const initializedRef = useRef(false);
  const onlineAgents = useMemo(
    () => agents.filter((agent) => agent.status === "online"),
    [agents],
  );
  const categorySelectOptions = useMemo(
    () =>
      categoryOptions.map((name) => ({
        label: name,
        value: name,
      })),
    [categoryOptions],
  );

  const syncAgentIds = useCallback(
    (value: unknown) => {
      const next = normalizeAgentIds(value, group);
      selectedAgentIdsRef.current = next;
      setSelectedAgentIds(next);
      form.setFieldValue("agentIds", next);
      form.validateFields(["agentIds"]).catch(() => undefined);
    },
    [form, group],
  );

  useEffect(() => {
    if (!open) {
      initializedRef.current = false;
      selectedAgentIdsRef.current = [];
      setSelectedAgentIds([]);
      form.resetFields();
      return;
    }
    if (initializedRef.current) return;
    initializedRef.current = true;
    const initialAgentIds = group
      ? onlineAgents.slice(0, Math.min(4, onlineAgents.length)).map((agent) => agent.id)
      : [];
    selectedAgentIdsRef.current = initialAgentIds;
    setSelectedAgentIds(initialAgentIds);
    form.setFieldsValue({
      agentIds: initialAgentIds,
      masterEnabled: true,
      folder: "Default",
    });
  }, [form, group, onlineAgents, open]);

  const submit = async () => {
    const latestAgentIds = selectedAgentIdsRef.current;
    form.setFieldValue("agentIds", latestAgentIds);
    const values = await form.validateFields();
    onCreate({
      title: values.title,
      agentIds: latestAgentIds,
      group,
      masterEnabled: values.masterEnabled ?? true,
      folder: normalizeConversationCategory(values.folder),
    });
    selectedAgentIdsRef.current = [];
    setSelectedAgentIds([]);
    form.resetFields();
  };

  return (
    <Modal
      title={group ? "新建多 Agent 群聊" : "新建 Agent 单聊"}
      open={open}
      onCancel={onCancel}
      onOk={submit}
      okText="创建"
      okButtonProps={{ "data-testid": "create-conversation-confirm" }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ masterEnabled: true, folder: "Default" }}
      >
        <Form.Item name="title" label="会话名称">
          <Input placeholder={group ? "多 Agent 协作-答辩演示" : "Agent 单聊"} />
        </Form.Item>
        <Form.Item name="folder" label="分类/文件夹">
          <Select options={categorySelectOptions} placeholder="选择左侧分类" />
        </Form.Item>
        <Form.Item
          name="agentIds"
          label={group ? "选择 2-8 个 Agent" : "选择 1 个 Agent"}
          rules={[
            {
              validator: async (_, value?: string[]) => {
                const count = value?.length ?? 0;
                if (group && (count < 2 || count > 8)) {
                  throw new Error("群聊需要选择 2-8 个 Agent");
                }
                if (!group && count !== 1) {
                  throw new Error("单聊需要选择 1 个 Agent");
                }
              },
            },
          ]}
        >
          <Select
            data-testid="agent-select"
            mode="multiple"
            maxCount={group ? 8 : 1}
            value={selectedAgentIds}
            placeholder="从 Agent 通讯录选择"
            onChange={syncAgentIds}
            onSelect={(value) => {
              const current = selectedAgentIdsRef.current;
              syncAgentIds(group ? [...current, String(value)] : [String(value)]);
            }}
            onDeselect={(value) => {
              syncAgentIds(
                selectedAgentIdsRef.current.filter((item) => item !== String(value)),
              );
            }}
            onBlur={() => {
              syncAgentIds(selectedAgentIdsRef.current);
            }}
            options={onlineAgents.map((agent) => ({
              label: `${agent.name} · ${agent.capabilities
                .slice(0, 2)
                .map((cap) => cap.label)
                .join("/")}`,
              value: agent.id,
            }))}
          />
        </Form.Item>
        {group && (
          <Form.Item name="masterEnabled" valuePropName="checked">
            <Checkbox>启用主控 Agent 自动拆解和调度</Checkbox>
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}
